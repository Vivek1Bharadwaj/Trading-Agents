"""WebSocket handler for streaming TradingAgents graph execution in real-time."""

import json
import os
import time
import datetime
import traceback
import asyncio
import logging
import queue
import threading

from fastapi import WebSocket, WebSocketDisconnect

from backend.schemas import AnalysisRequest
from backend.providers import get_provider_env_var

logger = logging.getLogger(__name__)


async def websocket_analysis_route(websocket: WebSocket):
    """Handle a WebSocket connection for a single analysis run.

    Protocol:
    1. Client connects and sends a JSON payload matching AnalysisRequest.
    2. Server streams real-time JSON messages as the graph executes (tool calls,
       analyst messages, debate speeches, section previews, agent status updates).
    3. Server sends a "complete" message when done, then cleanly finishes.
    """
    await websocket.accept()

    try:
        # ── 1. Receive and validate the analysis configuration ──────────
        data = await websocket.receive_text()
        try:
            config_dict = json.loads(data)
            req = AnalysisRequest(**config_dict)
        except Exception as e:
            await _send(websocket, "error", {"message": f"Invalid configuration: {e}"})
            await websocket.close()
            return

        # ── 2. Set the API key in the environment ───────────────────────
        env_var = get_provider_env_var(req.llm_provider)
        if env_var and req.api_key:
            os.environ[env_var] = req.api_key

        await _send(websocket, "status", {
            "message": f"Initializing analysis for {req.ticker}...",
            "phase": "init",
        })

        # ── 3. Build the config dict for the graph ─────────────────────
        from tradingagents.default_config import DEFAULT_CONFIG

        # Calibrate debate/risk rounds by depth to prevent runaway token burn
        depth_key = (req.research_depth or "shallow").strip().lower()
        if depth_key == "deep":
            max_debate_rounds = 2  # 2 Bull + 2 Bear = 4 turns
            max_risk_rounds = 2    # 2 Aggressive + 2 Conservative + 2 Neutral = 6 turns
        elif depth_key == "medium":
            max_debate_rounds = 1  # 1 Bull + 1 Bear = 2 turns
            max_risk_rounds = 2    # 2 Aggressive + 2 Conservative + 2 Neutral = 6 turns
        else:  # shallow or fallback
            max_debate_rounds = 1  # 1 Bull + 1 Bear = 2 turns
            max_risk_rounds = 1    # 1 Aggressive + 1 Conservative + 1 Neutral = 3 turns

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = req.llm_provider
        config["quick_think_llm"] = req.quick_think_llm
        config["deep_think_llm"] = req.deep_think_llm
        config["backend_url"] = req.backend_url
        config["max_debate_rounds"] = max_debate_rounds
        config["max_risk_discuss_rounds"] = max_risk_rounds
        config["output_language"] = req.output_language or "English"
        config["checkpoint_enabled"] = False
        config["llm_max_retries"] = 5  # Enable exponential backoff retries for 429 rate limits

        if req.openai_reasoning_effort:
            config["openai_reasoning_effort"] = req.openai_reasoning_effort
        if req.google_thinking_level:
            config["google_thinking_level"] = req.google_thinking_level
        if req.anthropic_effort:
            config["anthropic_effort"] = req.anthropic_effort

        # Map analyst display names to the keys the graph expects
        analyst_name_map = {
            "Market Analyst": "market",
            "Sentiment Analyst": "social",
            "News Analyst": "news",
            "Fundamentals Analyst": "fundamentals",
            "market": "market",
            "social": "social",
            "news": "news",
            "fundamentals": "fundamentals",
        }
        selected_analysts = []
        for a in req.analysts:
            key = analyst_name_map.get(a, a.lower())
            if key not in selected_analysts:
                selected_analysts.append(key)

        # Detect asset type
        crypto_suffixes = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
        ticker = req.ticker.strip().upper()
        asset_type = "crypto" if ticker.endswith(crypto_suffixes) else "stock"

        analysis_date = req.analysis_date or datetime.date.today().isoformat()

        # ── 4. Create the graph ─────────────────────────────────────────
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from backend.stats_handler import StatsCallbackHandler

            stats_handler = StatsCallbackHandler()

            graph = TradingAgentsGraph(
                selected_analysts=selected_analysts,
                config=config,
                debug=True,
                callbacks=[stats_handler],
            )
        except Exception as e:
            await _send(websocket, "error", {
                "message": f"Failed to initialize graph: {e}",
                "trace": traceback.format_exc(),
            })
            await websocket.close()
            return

        await _send(websocket, "status", {
            "message": "Graph compiled. Starting analysis...",
            "phase": "running",
        })

        # ── 5. Mark initial analyst statuses ────────────────────────────
        agent_display_map = {
            "market": "Market Analyst",
            "social": "Sentiment Analyst",
            "news": "News Analyst",
            "fundamentals": "Fundamentals Analyst",
        }
        for key in selected_analysts:
            name = agent_display_map.get(key, key)
            await _send(websocket, "agent_update", {"agent": name, "status": "in_progress"})

        # ── 6. Stream the graph execution in real-time ──────────────────
        start_time = time.time()
        report_sections = {}
        final_state = {}

        try:
            init_state = graph.create_run_state(ticker, analysis_date, asset_type)
            args = graph.propagator.get_graph_args(callbacks=[stats_handler])
            args["stream_mode"] = ["values", "tasks"]
            args["subgraphs"] = True
            
            if "config" not in args or not args["config"]:
                args["config"] = {}
            if "recursion_limit" not in args["config"]:
                args["config"]["recursion_limit"] = graph.propagator.max_recur_limit

            from tradingagents.dataflows.config import run_config_context
            context = run_config_context(config)

            event_queue = queue.Queue()

            def _stream_worker():
                """Worker thread that executes the synchronous graph stream."""
                try:
                    stream = context.run(graph.graph.stream, init_state, **args)
                    try:
                        while True:
                            step = context.run(next, stream, None)
                            if step is None:
                                break
                            event_queue.put(("step", step))
                    finally:
                        context.run(stream.close)
                    event_queue.put(("done", None))
                except Exception as exc:
                    event_queue.put(("error", (exc, traceback.format_exc())))

            worker_thread = threading.Thread(target=_stream_worker, daemon=True)
            worker_thread.start()

            seen_msg_ids = set()
            last_debate_speech = None
            last_risk_speech = None

            while True:
                try:
                    item = event_queue.get_nowait()
                except queue.Empty:
                    if not worker_thread.is_alive() and event_queue.empty():
                        break

                    # Emit periodic stats update
                    s = stats_handler.get_stats()
                    await _send(websocket, "stats", {
                        "llm_calls": s["llm_calls"],
                        "tool_calls": s["tool_calls"],
                        "tokens": {
                            "input": s["tokens_in"],
                            "output": s["tokens_out"],
                        },
                        "elapsed": round(time.time() - start_time, 1),
                    })
                    await asyncio.sleep(0.02)
                    continue

                kind, payload = item

                if kind == "done":
                    break
                elif kind == "error":
                    exc, tb = payload
                    logger.error(f"Execution error in stream thread: {exc}\n{tb}")
                    err_msg = str(exc)
                    if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                        err_msg = (
                            "Rate limit exceeded (429 RESOURCE_EXHAUSTED). "
                            "The free-tier quota for this model was reached. "
                            "Try choosing Gemini 2.0 Flash or Gemini 1.5 Flash in the setup wizard, or try again shortly."
                        )
                    elif "RecursionError" in err_msg or "recursion limit" in err_msg.lower():
                        rec_limit = args.get("config", {}).get("recursion_limit", 100)
                        err_msg = (
                            f"Agentic Loop Detected: An agent failed to resolve a task and hit the maximum step limit ({rec_limit}). "
                            "Analysis halted to prevent server crash."
                        )
                    await _send(websocket, "error", {"message": err_msg, "trace": tb})
                    return
                elif kind == "step":
                    namespace, mode, chunk = payload
                    now_ts = datetime.datetime.now().strftime("%H:%M:%S")

                    # ── Handle Analyst Subgraph Tasks ──────────────
                    if namespace:
                        result = chunk.get("result") if mode == "tasks" else None
                        if isinstance(result, dict):
                            analyst_key = None
                            for k in ("market", "social", "news", "fundamentals"):
                                if any(k in str(ns).lower() for ns in namespace):
                                    analyst_key = k
                                    break
                            analyst_name = agent_display_map.get(analyst_key, "Analyst") if analyst_key else "Analyst"

                            # 1. Inspect messages for tool calls and text
                            sub_msgs = result.get("messages", [])
                            if isinstance(sub_msgs, list):
                                for msg in sub_msgs:
                                    msg_id = getattr(msg, "id", None) or (type(msg).__name__, str(getattr(msg, "content", "")))
                                    if msg_id in seen_msg_ids:
                                        continue
                                    seen_msg_ids.add(msg_id)

                                    # Emit tool calls
                                    for tc in getattr(msg, "tool_calls", None) or []:
                                        await _send(websocket, "tool_call", {
                                            "tool": tc.get("name", "tool"),
                                            "args": tc.get("args", {}),
                                            "timestamp": now_ts,
                                        })

                                    # Emit message or tool result
                                    if msg.__class__.__name__ == "ToolMessage":
                                        tool_name = getattr(msg, "name", "Tool")
                                        content_str = str(msg.content or "")
                                        await _send(websocket, "message", {
                                            "sender": f"{tool_name} (Tool)",
                                            "content": (content_str[:300] + "...") if len(content_str) > 300 else content_str,
                                            "timestamp": now_ts,
                                        })
                                    else:
                                        content = getattr(msg, "content", "")
                                        if isinstance(content, str) and content.strip():
                                            await _send(websocket, "message", {
                                                "sender": analyst_name,
                                                "content": (content[:400] + "...") if len(content) > 400 else content,
                                                "timestamp": now_ts,
                                            })

                            # 2. Check if analyst produced its completed report
                            for r_key, a_name in [
                                ("market_report", "Market Analyst"),
                                ("sentiment_report", "Sentiment Analyst"),
                                ("news_report", "News Analyst"),
                                ("fundamentals_report", "Fundamentals Analyst"),
                            ]:
                                if result.get(r_key) and r_key not in report_sections:
                                    report_sections[r_key] = result[r_key]
                                    final_state[r_key] = result[r_key]
                                    await _send(websocket, "report_section", {
                                        "section": r_key, "content": result[r_key]
                                    })
                                    await _send(websocket, "agent_update", {
                                        "agent": a_name, "status": "completed"
                                    })
                                    await _send(websocket, "message", {
                                        "sender": a_name,
                                        "content": f"Completed {a_name} report.",
                                        "timestamp": now_ts,
                                    })

                    # ── Handle Top-Level Values ────────────────────
                    elif mode == "values" and isinstance(chunk, dict):
                        final_state.update(chunk)

                        # 1. Bull/Bear Investment Debate
                        if chunk.get("investment_debate_state"):
                            ds = chunk["investment_debate_state"]
                            current_resp = ds.get("current_response", "")
                            if current_resp and current_resp != last_debate_speech:
                                last_debate_speech = current_resp
                                speaker = "Bull Researcher" if current_resp.startswith("Bull") else "Bear Researcher"
                                speech_text = current_resp.split(":", 1)[1].strip() if ":" in current_resp else current_resp
                                await _send(websocket, "agent_update", {"agent": speaker, "status": "in_progress"})
                                await _send(websocket, "message", {
                                    "sender": speaker,
                                    "content": (speech_text[:400] + "...") if len(speech_text) > 400 else speech_text,
                                    "timestamp": now_ts,
                                })

                            if ds.get("bull_history") and report_sections.get("bull_research") != ds["bull_history"]:
                                report_sections["bull_research"] = ds["bull_history"]
                                await _send(websocket, "report_section", {"section": "bull_research", "content": ds["bull_history"]})

                            if ds.get("bear_history") and report_sections.get("bear_research") != ds["bear_history"]:
                                report_sections["bear_research"] = ds["bear_history"]
                                await _send(websocket, "report_section", {"section": "bear_research", "content": ds["bear_history"]})

                        # 2. Research Manager
                        if chunk.get("investment_plan") and "investment_plan" not in report_sections:
                            report_sections["investment_plan"] = chunk["investment_plan"]
                            await _send(websocket, "report_section", {"section": "investment_plan", "content": chunk["investment_plan"]})
                            await _send(websocket, "agent_update", {"agent": "Bull Researcher", "status": "completed"})
                            await _send(websocket, "agent_update", {"agent": "Bear Researcher", "status": "completed"})
                            await _send(websocket, "agent_update", {"agent": "Research Manager", "status": "completed"})
                            await _send(websocket, "message", {
                                "sender": "Research Manager",
                                "content": "Investment plan finalized.",
                                "timestamp": now_ts,
                            })
                            await _send(websocket, "agent_update", {"agent": "Trader", "status": "in_progress"})

                        # 3. Trader
                        if chunk.get("trader_investment_plan") and "trader_plan" not in report_sections:
                            report_sections["trader_plan"] = chunk["trader_investment_plan"]
                            await _send(websocket, "report_section", {"section": "trader_plan", "content": chunk["trader_investment_plan"]})
                            await _send(websocket, "agent_update", {"agent": "Trader", "status": "completed"})
                            await _send(websocket, "message", {
                                "sender": "Trader",
                                "content": "Trading plan formulated.",
                                "timestamp": now_ts,
                            })
                            await _send(websocket, "agent_update", {"agent": "Aggressive Analyst", "status": "in_progress"})

                        # 4. Risk Debate
                        if chunk.get("risk_debate_state"):
                            rs = chunk["risk_debate_state"]
                            speaker = rs.get("latest_speaker")
                            if speaker:
                                await _send(websocket, "agent_update", {"agent": speaker, "status": "in_progress"})

                            history = rs.get("history", "")
                            if history and history != last_risk_speech:
                                last_risk_speech = history
                                lines = [l for l in history.strip().split("\n") if l.strip()]
                                if lines:
                                    last_line = lines[-1]
                                    spk = speaker or "Risk Analyst"
                                    txt = last_line
                                    if ":" in last_line:
                                        cand_spk, cand_txt = last_line.split(":", 1)
                                        if any(k in cand_spk for k in ("Aggressive", "Conservative", "Neutral")):
                                            spk = cand_spk.strip()
                                            txt = cand_txt.strip()
                                    await _send(websocket, "message", {
                                        "sender": spk,
                                        "content": (txt[:400] + "...") if len(txt) > 400 else txt,
                                        "timestamp": now_ts,
                                    })

                        # 5. Final Decision
                        if chunk.get("final_trade_decision") and "final_decision" not in report_sections:
                            report_sections["final_decision"] = chunk["final_trade_decision"]
                            await _send(websocket, "report_section", {"section": "final_decision", "content": chunk["final_trade_decision"]})
                            for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"):
                                await _send(websocket, "agent_update", {"agent": agent, "status": "completed"})
                            await _send(websocket, "message", {
                                "sender": "Portfolio Manager",
                                "content": "Final risk evaluation complete and decision signed off.",
                                "timestamp": now_ts,
                            })

            # ── 7. Rating and final report assembly ─────────────────────
            from tradingagents.agents.rating import run_rating
            rating = run_rating(final_state) if final_state else "REVIEW"

            try:
                graph.record_decision(ticker, analysis_date, final_state)
            except Exception as rec_err:
                logger.warning(f"Failed to record decision: {rec_err}")

            saved_report_path = None
            try:
                saved_report_path = str(graph.save_reports(final_state, ticker))
                logger.info(f"Successfully saved analysis reports to {saved_report_path}")
            except Exception as rep_err:
                logger.warning(f"Failed to save reports to disk: {rep_err}")

            # Send final stats
            elapsed = time.time() - start_time
            s = stats_handler.get_stats()
            stats = {
                "llm_calls": s["llm_calls"],
                "tool_calls": s["tool_calls"],
                "tokens": {
                    "input": s["tokens_in"],
                    "output": s["tokens_out"],
                },
                "elapsed": round(elapsed, 1),
            }
            await _send(websocket, "stats", stats)

            # Build and send complete report
            complete_report = _build_complete_report(final_state, report_sections)

            await _send(websocket, "complete", {
                "rating": rating,
                "report": complete_report,
                "report_path": saved_report_path,
                "sections": report_sections,
            })

        except Exception as e:
            logger.exception("Analysis execution error")
            await _send(websocket, "error", {
                "message": f"Execution error: {e}",
                "trace": traceback.format_exc(),
            })

    except WebSocketDisconnect:
        logger.info("Client disconnected during analysis")
    except Exception as e:
        logger.exception("Unexpected WebSocket error")
        try:
            await _send(websocket, "error", {"message": f"Internal error: {e}"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _send(ws: WebSocket, msg_type: str, data: dict):
    """Send a typed JSON message over the WebSocket."""
    try:
        await ws.send_json({"type": msg_type, "data": data})
    except Exception:
        pass


def _build_complete_report(final_state: dict, sections: dict) -> str:
    """Assemble a markdown report from the final state and collected sections."""
    parts = []

    for key, title in [
        ("market_report", "Market Analysis"),
        ("sentiment_report", "Sentiment Analysis"),
        ("news_report", "News Analysis"),
        ("fundamentals_report", "Fundamentals Analysis"),
    ]:
        content = final_state.get(key) or sections.get(key)
        if content:
            parts.append(f"## {title}\n\n{content}")

    if sections.get("bull_research"):
        parts.append(f"## Bull Research\n\n{sections['bull_research']}")
    if sections.get("bear_research"):
        parts.append(f"## Bear Research\n\n{sections['bear_research']}")
    if final_state.get("investment_plan") or sections.get("investment_plan"):
        parts.append(f"## Investment Plan\n\n{final_state.get('investment_plan') or sections.get('investment_plan')}")
    if final_state.get("trader_investment_plan") or sections.get("trader_plan"):
        parts.append(f"## Trading Plan\n\n{final_state.get('trader_investment_plan') or sections.get('trader_plan')}")
    if final_state.get("final_trade_decision") or sections.get("final_decision"):
        parts.append(f"## Final Decision\n\n{final_state.get('final_trade_decision') or sections.get('final_decision')}")

    return "\n\n---\n\n".join(parts) if parts else "No report content available."
