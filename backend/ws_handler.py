"""WebSocket handler for streaming TradingAgents graph execution in real-time."""

import asyncio
import datetime
import gc
import json
import logging
import os
import queue
import threading
import time
import traceback

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
    send_lock = asyncio.Lock()
    cancel_event = threading.Event()
    receiver_task: asyncio.Task | None = None

    try:
        # ── 1. Receive and validate the analysis configuration ──────────
        data = await websocket.receive_text()
        try:
            config_dict = json.loads(data)
            req = AnalysisRequest(**config_dict)
        except Exception as e:
            await _send(websocket, "error", {"message": f"Invalid configuration: {e}"}, send_lock, cancel_event)
            await websocket.close()
            return

        # Keep reading client messages (e.g., heartbeats) so uvicorn never pauses
        # socket reads and triggers keepalive ping timeouts mid-analysis.
        receiver_task = asyncio.create_task(
            _drain_client_messages(websocket, cancel_event, send_lock)
        )

        # ── 2. Set the API key in the environment ───────────────────────
        env_var = get_provider_env_var(req.llm_provider)
        if env_var and req.api_key:
            os.environ[env_var] = req.api_key

        async def emit(msg_type: str, payload: dict) -> bool:
            return await _send(websocket, msg_type, payload, send_lock, cancel_event)

        await emit("status", {
            "message": f"Initializing analysis for {req.ticker}...",
            "phase": "init",
        })

        # ── 3. Build the config dict for the graph ─────────────────────
        from tradingagents.default_config import DEFAULT_CONFIG

        # Calibrate debate/risk rounds and tool limits by depth to prevent runaway token burn
        depth_key = (req.research_depth or "shallow").strip().lower()
        if depth_key == "deep":
            max_debate_rounds = 2  # 2 Bull + 2 Bear = 4 turns
            max_risk_rounds = 2    # 2 Aggressive + 2 Conservative + 2 Neutral = 6 turns
            max_tool_rounds = 4    # Optimized for Render free tier memory/rate limits
        elif depth_key == "medium":
            max_debate_rounds = 1  # 1 Bull + 1 Bear = 2 turns
            max_risk_rounds = 2    # 2 Aggressive + 2 Conservative + 2 Neutral = 6 turns
            max_tool_rounds = 3
        else:  # shallow or fallback
            max_debate_rounds = 1  # 1 Bull + 1 Bear = 2 turns
            max_risk_rounds = 1    # 1 Aggressive + 1 Conservative + 1 Neutral = 3 turns
            max_tool_rounds = 2

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = req.llm_provider
        config["quick_think_llm"] = req.quick_think_llm
        config["deep_think_llm"] = req.deep_think_llm
        config["backend_url"] = req.backend_url
        config["max_debate_rounds"] = max_debate_rounds
        config["max_risk_discuss_rounds"] = max_risk_rounds
        config["max_tool_rounds"] = max_tool_rounds
        config["output_language"] = req.output_language or "English"
        config["checkpoint_enabled"] = False
        config["llm_max_retries"] = 2  # Fast single retry to avoid multi-minute UI freezes on 429/503
        config["llm_timeout"] = 60     # Fail hung model calls within 60s instead of waiting 10 minutes

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

            graph = await asyncio.to_thread(
                TradingAgentsGraph,
                selected_analysts=selected_analysts,
                config=config,
                debug=True,
                callbacks=[stats_handler],
            )
        except Exception as e:
            await emit("error", {
                "message": f"Failed to initialize graph: {e}",
                "trace": traceback.format_exc(),
            })
            return

        if cancel_event.is_set():
            return

        await emit("status", {
            "message": "Graph compiled. Starting analysis...",
            "phase": "running",
        })

        # ── 5. Mark initial analyst statuses ────────────────────────────
        agent_display_map = {
            "market": "Market Analyst",
            "social": "Sentiment Analyst",
            "sentiment": "Sentiment Analyst",
            "news": "News Analyst",
            "fundamentals": "Fundamentals Analyst",
        }
        risk_speaker_map = {
            "Aggressive": "Aggressive Analyst",
            "Conservative": "Conservative Analyst",
            "Neutral": "Neutral Analyst",
            "Aggressive Analyst": "Aggressive Analyst",
            "Conservative Analyst": "Conservative Analyst",
            "Neutral Analyst": "Neutral Analyst",
        }
        for key in selected_analysts:
            name = agent_display_map.get(key, key)
            await emit("agent_update", {"agent": name, "status": "in_progress"})

        # ── 6. Stream the graph execution in real-time ──────────────────
        start_time = time.time()
        report_sections = {}
        final_state = {}

        try:
            init_state = await asyncio.to_thread(
                graph.create_run_state, ticker, analysis_date, asset_type
            )
            if cancel_event.is_set():
                return

            args = graph.propagator.get_graph_args(callbacks=[stats_handler])
            args["stream_mode"] = ["values", "tasks"]
            args["subgraphs"] = True
<<<<<<< HEAD

            # Hard circuit breaker: inject recursion_limit from config (default 100)
            if "config" not in args or not args["config"]:
                args["config"] = {}
            args["config"]["recursion_limit"] = int(config.get("max_recur_limit", 100))
=======
            
            if "config" not in args or not args["config"]:
                args["config"] = {}
            if "recursion_limit" not in args["config"]:
                args["config"]["recursion_limit"] = graph.propagator.max_recur_limit
>>>>>>> origin/main

            from tradingagents.dataflows.config import run_config_context
            context = run_config_context(config)

            event_queue = queue.Queue()

            def _stream_worker():
                """Worker thread that executes the synchronous graph stream."""
                try:
                    stream = context.run(graph.graph.stream, init_state, **args)
                    try:
                        while not cancel_event.is_set():
                            step = context.run(next, stream, None)
                            if step is None or cancel_event.is_set():
                                break
                            event_queue.put(("step", step))
                    finally:
                        context.run(stream.close)
                    if not cancel_event.is_set():
                        event_queue.put(("done", None))
                except Exception as exc:
                    if not cancel_event.is_set():
                        event_queue.put(("error", (exc, traceback.format_exc())))

            worker_thread = threading.Thread(target=_stream_worker, daemon=True)
            worker_thread.start()

            seen_msg_ids = set()
            last_debate_speech = None
            last_risk_key = None
            research_mgr_started = False
            portfolio_mgr_started = False
            last_stats_time = start_time
            last_keepalive_time = start_time

            async def _flush_warnings() -> None:
                for warn_msg in stats_handler.pop_warnings():
                    await emit("message", {
                        "sender": "System",
                        "content": warn_msg,
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    })

            while not cancel_event.is_set():
                await _flush_warnings()

                try:
                    item = event_queue.get_nowait()
                except queue.Empty:
                    if not worker_thread.is_alive() and event_queue.empty():
                        break

<<<<<<< HEAD
                    now = time.time()
                    # Emit throttled stats update once per second
                    if now - last_stats_time >= 1.0:
                        last_stats_time = now
                        s = stats_handler.get_stats()
                        if not await emit("stats", {
                            "llm_calls": s["llm_calls"],
                            "tool_calls": s["tool_calls"],
                            "tokens": {
                                "input": s["tokens_in"],
                                "output": s["tokens_out"],
                            },
                            "elapsed": round(now - start_time, 1),
                        }):
                            break

                    # Send periodic keepalive heartbeat every 5s to prevent proxy idle timeout
                    if now - last_keepalive_time >= 5.0:
                        last_keepalive_time = now
                        if not await emit("status", {
                            "message": "Analysis running...",
                            "phase": "running",
                            "heartbeat": True,
                        }):
                            break

                    await asyncio.sleep(0.2)
=======
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
>>>>>>> origin/main
                    continue

                kind, payload = item

                if kind == "done":
                    await _flush_warnings()
                    break
                elif kind == "error":
                    exc, tb = payload
                    logger.error(f"Execution error in stream thread: {exc}\n{tb}")
                    from tradingagents.llm_clients.base_client import classify_fatal_llm_error

                    fatal = classify_fatal_llm_error(exc)
                    err_msg = fatal or str(exc)
                    if not fatal and ("RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg):
                        err_msg = (
                            "Rate limit exceeded (429 RESOURCE_EXHAUSTED). "
                            "The free-tier quota for this model was reached. "
                            "Try a lighter model (e.g. gemini-3.5-flash-lite), Shallow mode, or retry in a minute."
                        )
                    elif "RecursionError" in err_msg or "recursion limit" in err_msg.lower():
                        rec_limit = args.get("config", {}).get("recursion_limit", 100)
                        err_msg = (
<<<<<<< HEAD
                            "Agentic Loop Detected: An agent exceeded the safety step limit. "
                            "Analysis halted to prevent server crash."
                        )
                    await emit("error", {"message": err_msg, "trace": tb})
                    await asyncio.sleep(0.2)
=======
                            f"Agentic Loop Detected: An agent failed to resolve a task and hit the maximum step limit ({rec_limit}). "
                            "Analysis halted to prevent server crash."
                        )
                    await _send(websocket, "error", {"message": err_msg, "trace": tb})
>>>>>>> origin/main
                    return
                elif kind == "step":
                    namespace, mode, chunk = payload
                    now_ts = datetime.datetime.now().strftime("%H:%M:%S")

                    # ── Handle Analyst Subgraph Tasks ──────────────
                    if namespace:
                        result = chunk.get("result") if mode == "tasks" else None
                        if isinstance(result, dict):
                            analyst_key = None
                            ns_text = " ".join(str(ns).lower() for ns in namespace)
                            for k in ("market", "social", "sentiment", "news", "fundamentals"):
                                if k in ns_text:
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
                                        await emit("tool_call", {
                                            "tool": tc.get("name", "tool"),
                                            "args": tc.get("args", {}),
                                            "timestamp": now_ts,
                                        })

                                    # Emit message or tool result
                                    if msg.__class__.__name__ == "ToolMessage":
                                        tool_name = getattr(msg, "name", "Tool")
                                        content_str = _extract_text(msg.content)
                                        await emit("message", {
                                            "sender": f"{tool_name} (Tool)",
                                            "content": (content_str[:300] + "...") if len(content_str) > 300 else content_str,
                                            "timestamp": now_ts,
                                        })
                                    else:
                                        content = _extract_text(getattr(msg, "content", ""))
                                        if content.strip():
                                            await emit("message", {
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
                                    await emit("report_section", {
                                        "section": r_key, "content": result[r_key]
                                    })
                                    await emit("agent_update", {
                                        "agent": a_name, "status": "completed"
                                    })
                                    await emit("message", {
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
                            debate_count = int(ds.get("count", 0) or 0)
                            max_debate_allowed = 2 * max_debate_rounds

                            if current_resp and current_resp != last_debate_speech and "investment_plan" not in report_sections:
                                last_debate_speech = current_resp
                                speaker = "Bull Researcher" if current_resp.startswith("Bull") else "Bear Researcher"
                                speech_text = current_resp.split(":", 1)[1].strip() if ":" in current_resp else current_resp
                                await emit("message", {
                                    "sender": speaker,
                                    "content": (speech_text[:400] + "...") if len(speech_text) > 400 else speech_text,
                                    "timestamp": now_ts,
                                })

                                if debate_count >= max_debate_allowed and not research_mgr_started:
                                    research_mgr_started = True
                                    await emit("agent_update", {"agent": "Bull Researcher", "status": "completed"})
                                    await emit("agent_update", {"agent": "Bear Researcher", "status": "completed"})
                                    await emit("agent_update", {"agent": "Research Manager", "status": "in_progress"})
                                    await emit("message", {
                                        "sender": "Research Manager",
                                        "content": "Investment debate complete. Synthesizing investment plan...",
                                        "timestamp": now_ts,
                                    })
                                elif debate_count < max_debate_allowed:
                                    next_debater = "Bear Researcher" if speaker == "Bull Researcher" else "Bull Researcher"
                                    await emit("agent_update", {"agent": speaker, "status": "completed"})
                                    await emit("agent_update", {"agent": next_debater, "status": "in_progress"})

                            if ds.get("bull_history") and report_sections.get("bull_research") != ds["bull_history"]:
                                report_sections["bull_research"] = ds["bull_history"]
                                await emit("report_section", {"section": "bull_research", "content": ds["bull_history"]})

                            if ds.get("bear_history") and report_sections.get("bear_research") != ds["bear_history"]:
                                report_sections["bear_research"] = ds["bear_history"]
                                await emit("report_section", {"section": "bear_research", "content": ds["bear_history"]})

                        # 2. Research Manager
                        if chunk.get("investment_plan") and "investment_plan" not in report_sections:
                            report_sections["investment_plan"] = chunk["investment_plan"]
                            await emit("report_section", {"section": "investment_plan", "content": chunk["investment_plan"]})
                            await emit("agent_update", {"agent": "Bull Researcher", "status": "completed"})
                            await emit("agent_update", {"agent": "Bear Researcher", "status": "completed"})
                            await emit("agent_update", {"agent": "Research Manager", "status": "completed"})
                            await emit("message", {
                                "sender": "Research Manager",
                                "content": "Investment plan finalized.",
                                "timestamp": now_ts,
                            })
                            await emit("agent_update", {"agent": "Trader", "status": "in_progress"})

                        # 3. Trader
                        if chunk.get("trader_investment_plan") and "trader_plan" not in report_sections:
                            report_sections["trader_plan"] = chunk["trader_investment_plan"]
                            await emit("report_section", {"section": "trader_plan", "content": chunk["trader_investment_plan"]})
                            await emit("agent_update", {"agent": "Trader", "status": "completed"})
                            await emit("message", {
                                "sender": "Trader",
                                "content": "Trading plan formulated.",
                                "timestamp": now_ts,
                            })
                            await emit("agent_update", {"agent": "Aggressive Analyst", "status": "in_progress"})

                        # 4. Risk Debate
                        if chunk.get("risk_debate_state") and "final_decision" not in report_sections:
                            rs = chunk["risk_debate_state"]
                            raw_speaker = rs.get("latest_speaker")
                            risk_count = int(rs.get("count", 0) or 0)
                            max_risk_allowed = 3 * max_risk_rounds
                            history = rs.get("history", "")

                            turn_key = (risk_count, raw_speaker, history)
                            if raw_speaker and raw_speaker != "Judge" and turn_key != last_risk_key:
                                last_risk_key = turn_key
                                mapped_speaker = risk_speaker_map.get(raw_speaker, raw_speaker)

                                role_resp_map = {
                                    "Aggressive Analyst": rs.get("current_aggressive_response", ""),
                                    "Conservative Analyst": rs.get("current_conservative_response", ""),
                                    "Neutral Analyst": rs.get("current_neutral_response", ""),
                                }
                                raw_speech = role_resp_map.get(mapped_speaker, "")
                                if raw_speech:
                                    txt = raw_speech.split(":", 1)[1].strip() if ":" in raw_speech else raw_speech.strip()
                                else:
                                    lines = [l for l in history.strip().split("\n") if l.strip()]
                                    txt = lines[-1] if lines else ""

                                if txt:
                                    await emit("message", {
                                        "sender": mapped_speaker,
                                        "content": (txt[:400] + "...") if len(txt) > 400 else txt,
                                        "timestamp": now_ts,
                                    })

                                if risk_count >= max_risk_allowed:
                                    for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
                                        await emit("agent_update", {"agent": agent, "status": "completed"})
                                    if not portfolio_mgr_started:
                                        portfolio_mgr_started = True
                                        await emit("agent_update", {"agent": "Portfolio Manager", "status": "in_progress"})
                                        await emit("message", {
                                            "sender": "Portfolio Manager",
                                            "content": "Risk debate complete. Synthesizing final risk evaluation and rating...",
                                            "timestamp": now_ts,
                                        })
                                else:
                                    next_map = {
                                        "Aggressive Analyst": "Conservative Analyst",
                                        "Conservative Analyst": "Neutral Analyst",
                                        "Neutral Analyst": "Aggressive Analyst",
                                    }
                                    await emit("agent_update", {"agent": mapped_speaker, "status": "completed"})
                                    next_speaker = next_map.get(mapped_speaker)
                                    if next_speaker:
                                        await emit("agent_update", {"agent": next_speaker, "status": "in_progress"})

                        # 5. Final Decision
                        if chunk.get("final_trade_decision") and "final_decision" not in report_sections:
                            report_sections["final_decision"] = chunk["final_trade_decision"]
                            await emit("report_section", {"section": "final_decision", "content": chunk["final_trade_decision"]})
                            for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"):
                                await emit("agent_update", {"agent": agent, "status": "completed"})
                            await emit("message", {
                                "sender": "Portfolio Manager",
                                "content": "Final risk evaluation complete and decision signed off.",
                                "timestamp": now_ts,
                            })

            if cancel_event.is_set():
                logger.info("Client disconnected during analysis; skipping final assembly")
                return

            # ── 7. Rating and final report assembly ─────────────────────
            from tradingagents.agents.rating import run_rating
            rating = await asyncio.to_thread(run_rating, final_state) if final_state else "REVIEW"

            try:
<<<<<<< HEAD
                await asyncio.to_thread(graph.record_decision, ticker, analysis_date, final_state)
            except Exception:
                pass
=======
                graph.record_decision(ticker, analysis_date, final_state)
            except Exception as rec_err:
                logger.warning(f"Failed to record decision: {rec_err}")

            saved_report_path = None
            try:
                saved_report_path = str(graph.save_reports(final_state, ticker))
                logger.info(f"Successfully saved analysis reports to {saved_report_path}")
            except Exception as rep_err:
                logger.warning(f"Failed to save reports to disk: {rep_err}")
>>>>>>> origin/main

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
            await emit("stats", stats)

            # Build and send complete report
            complete_report = _build_complete_report(final_state, report_sections)

            await emit("complete", {
                "rating": rating,
                "report": complete_report,
                "report_path": saved_report_path,
                "sections": report_sections,
            })

        except Exception as e:
            logger.exception("Analysis execution error")
            await emit("error", {
                "message": f"Execution error: {e}",
                "trace": traceback.format_exc(),
            })

    except WebSocketDisconnect:
        cancel_event.set()
        logger.info("Client disconnected during analysis")
    except Exception as e:
        cancel_event.set()
        logger.exception("Unexpected WebSocket error")
        try:
            await _send(websocket, "error", {"message": f"Internal error: {e}"}, send_lock, cancel_event)
        except Exception:
            pass
    finally:
        cancel_event.set()
        if receiver_task is not None and not receiver_task.done():
            receiver_task.cancel()
            await asyncio.gather(receiver_task, return_exceptions=True)
        try:
            await websocket.close()
        except Exception:
            pass
        gc.collect()


async def _drain_client_messages(
    ws: WebSocket,
    cancel_event: threading.Event,
    send_lock: asyncio.Lock,
) -> None:
    """Continuously drain incoming client WebSocket messages during analysis.

    Calling ``receive()`` keeps Uvicorn's Sans-IO transport unpaused so
    protocol-level PING/PONG keepalives are read promptly instead of timing out
    after 40 seconds, and signals ``cancel_event`` if the client disconnects.
    """
    try:
        while not cancel_event.is_set():
            msg = await ws.receive()
            msg_type = msg.get("type")
            if msg_type == "websocket.disconnect":
                cancel_event.set()
                break
            text = msg.get("text")
            if text:
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict) and payload.get("type") == "ping":
                        await _send(ws, "pong", {}, send_lock, cancel_event)
                except json.JSONDecodeError:
                    pass
    except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
        cancel_event.set()
    except Exception:
        cancel_event.set()


def _extract_text(content: object) -> str:
    """Normalize LangChain message content (str or content-block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        return "\n".join(parts)
    return str(content or "")


async def _send(
    ws: WebSocket,
    msg_type: str,
    data: dict,
    send_lock: asyncio.Lock | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    """Send a typed JSON message over the WebSocket, returning False if disconnected."""
    if cancel_event is not None and cancel_event.is_set():
        return False
    try:
        if send_lock is not None:
            async with send_lock:
                await ws.send_json({"type": msg_type, "data": data})
        else:
            await ws.send_json({"type": msg_type, "data": data})
        return True
    except Exception:
        if cancel_event is not None:
            cancel_event.set()
        return False


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
