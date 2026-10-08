"""WebSocket handler for streaming TradingAgents graph execution in real-time."""

import json
import os
import time
import datetime
import traceback
import asyncio
import logging
from functools import partial

from fastapi import WebSocket, WebSocketDisconnect

from backend.schemas import AnalysisRequest
from backend.providers import get_provider_env_var

logger = logging.getLogger(__name__)


async def websocket_analysis_route(websocket: WebSocket):
    """Handle a WebSocket connection for a single analysis run.

    Protocol:
    1. Client connects and sends a JSON payload matching AnalysisRequest.
    2. Server streams JSON messages as the graph executes.
    3. Server sends a "complete" message when done, then closes.
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

        # ── 3. Build the config dict the same way cli/run.py does ───────
        from tradingagents.default_config import DEFAULT_CONFIG

        depth_map = {"Shallow": 1, "Medium": 3, "Deep": 5}
        depth = depth_map.get(req.research_depth, 1)

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = req.llm_provider
        config["quick_think_llm"] = req.quick_think_llm
        config["deep_think_llm"] = req.deep_think_llm
        config["backend_url"] = req.backend_url
        config["max_debate_rounds"] = depth
        config["max_risk_discuss_rounds"] = depth
        config["output_language"] = req.output_language or "English"
        config["checkpoint_enabled"] = False

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
            # Also accept the raw keys directly
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
            from cli.stats_handler import StatsCallbackHandler

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

        # ── 6. Stream the graph execution ───────────────────────────────
        start_time = time.time()
        report_sections = {}
        final_state = {}

        try:
            init_state = graph.create_run_state(ticker, analysis_date, asset_type)
            args = graph.propagator.get_graph_args(callbacks=[stats_handler])

            from tradingagents.dataflows.config import run_config_context
            context = run_config_context(config)

            def _run_stream():
                """Run the synchronous graph stream in a thread."""
                nonlocal final_state
                trace = []
                stream = context.run(
                    graph.graph.stream, init_state, subgraphs=True,
                    stream_mode=["values", "tasks"], **args,
                )
                try:
                    while True:
                        step = context.run(next, stream, None)
                        if step is None:
                            break
                        trace.append(step)
                finally:
                    context.run(stream.close)
                return trace

            # Run the blocking graph in a thread, periodically sending updates
            loop = asyncio.get_event_loop()
            stream_task = loop.run_in_executor(None, _run_stream)

            # Poll for stats updates while the stream runs
            while not stream_task.done():
                elapsed = time.time() - start_time
                try:
                    stats = {
                        "llm_calls": getattr(stats_handler, "llm_call_count", 0),
                        "tool_calls": getattr(stats_handler, "tool_call_count", 0),
                        "tokens": {
                            "input": getattr(stats_handler, "input_tokens", 0),
                            "output": getattr(stats_handler, "output_tokens", 0),
                        },
                        "elapsed": round(elapsed, 1),
                    }
                    await _send(websocket, "stats", stats)
                except Exception:
                    pass
                await asyncio.sleep(2)

            # Get the trace results
            trace = await stream_task

            # ── 7. Process the trace into report sections ───────────────
            for step in trace:
                namespace, mode, chunk = step

                if namespace:
                    # Subgraph (analyst) step
                    result = chunk.get("result") if mode == "tasks" else None
                    if isinstance(result, dict):
                        for key in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
                            if result.get(key):
                                report_sections[key] = result[key]
                                await _send(websocket, "report_section", {
                                    "section": key, "content": result[key]
                                })
                                agent_key = key.replace("_report", "")
                                agent_name = agent_display_map.get(agent_key, agent_key)
                                await _send(websocket, "agent_update", {
                                    "agent": agent_name, "status": "completed"
                                })
                elif mode == "values" and isinstance(chunk, dict):
                    final_state.update(chunk)

                    # Investment debate
                    if chunk.get("investment_debate_state"):
                        ds = chunk["investment_debate_state"]
                        if ds.get("bull_history"):
                            report_sections["bull_research"] = ds["bull_history"]
                            await _send(websocket, "report_section", {
                                "section": "bull_research", "content": ds["bull_history"]
                            })
                            await _send(websocket, "agent_update", {
                                "agent": "Bull Researcher", "status": "in_progress"
                            })
                        if ds.get("bear_history"):
                            report_sections["bear_research"] = ds["bear_history"]
                            await _send(websocket, "report_section", {
                                "section": "bear_research", "content": ds["bear_history"]
                            })
                            await _send(websocket, "agent_update", {
                                "agent": "Bear Researcher", "status": "in_progress"
                            })

                    if chunk.get("investment_plan"):
                        report_sections["investment_plan"] = chunk["investment_plan"]
                        await _send(websocket, "report_section", {
                            "section": "investment_plan", "content": chunk["investment_plan"]
                        })
                        await _send(websocket, "agent_update", {"agent": "Research Manager", "status": "completed"})
                        await _send(websocket, "agent_update", {"agent": "Bull Researcher", "status": "completed"})
                        await _send(websocket, "agent_update", {"agent": "Bear Researcher", "status": "completed"})

                    if chunk.get("trader_investment_plan"):
                        report_sections["trader_plan"] = chunk["trader_investment_plan"]
                        await _send(websocket, "report_section", {
                            "section": "trader_plan", "content": chunk["trader_investment_plan"]
                        })
                        await _send(websocket, "agent_update", {"agent": "Trader", "status": "completed"})

                    # Risk debate
                    if chunk.get("risk_debate_state"):
                        rs = chunk["risk_debate_state"]
                        if rs.get("aggressive_history"):
                            await _send(websocket, "agent_update", {"agent": "Aggressive Analyst", "status": "in_progress"})
                        if rs.get("conservative_history"):
                            await _send(websocket, "agent_update", {"agent": "Conservative Analyst", "status": "in_progress"})
                        if rs.get("neutral_history"):
                            await _send(websocket, "agent_update", {"agent": "Neutral Analyst", "status": "in_progress"})

                    if chunk.get("final_trade_decision"):
                        report_sections["final_decision"] = chunk["final_trade_decision"]
                        await _send(websocket, "report_section", {
                            "section": "final_decision", "content": chunk["final_trade_decision"]
                        })
                        for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"):
                            await _send(websocket, "agent_update", {"agent": agent, "status": "completed"})

            # ── 8. Extract rating and send final result ─────────────────
            from tradingagents.agents.rating import run_rating
            rating = run_rating(final_state) if final_state else "REVIEW"

            # Record the decision
            try:
                graph.record_decision(ticker, analysis_date, final_state)
            except Exception:
                pass

            # Send final stats
            elapsed = time.time() - start_time
            stats = {
                "llm_calls": getattr(stats_handler, "llm_call_count", 0),
                "tool_calls": getattr(stats_handler, "tool_call_count", 0),
                "tokens": {
                    "input": getattr(stats_handler, "input_tokens", 0),
                    "output": getattr(stats_handler, "output_tokens", 0),
                },
                "elapsed": round(elapsed, 1),
            }
            await _send(websocket, "stats", stats)

            # Build the complete report text
            complete_report = _build_complete_report(final_state, report_sections)

            await _send(websocket, "complete", {
                "rating": rating,
                "report": complete_report,
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

    if final_state.get("market_report"):
        parts.append(f"## Market Analysis\n\n{final_state['market_report']}")
    if final_state.get("sentiment_report"):
        parts.append(f"## Sentiment Analysis\n\n{final_state['sentiment_report']}")
    if final_state.get("news_report"):
        parts.append(f"## News Analysis\n\n{final_state['news_report']}")
    if final_state.get("fundamentals_report"):
        parts.append(f"## Fundamentals Analysis\n\n{final_state['fundamentals_report']}")

    if sections.get("bull_research"):
        parts.append(f"## Bull Research\n\n{sections['bull_research']}")
    if sections.get("bear_research"):
        parts.append(f"## Bear Research\n\n{sections['bear_research']}")
    if final_state.get("investment_plan"):
        parts.append(f"## Investment Plan\n\n{final_state['investment_plan']}")
    if final_state.get("trader_investment_plan"):
        parts.append(f"## Trading Plan\n\n{final_state['trader_investment_plan']}")
    if final_state.get("final_trade_decision"):
        parts.append(f"## Final Decision\n\n{final_state['final_trade_decision']}")

    return "\n\n---\n\n".join(parts) if parts else "No report content available."
