"""WebSocket handler for streaming TradingAgents graph execution in real-time."""

import asyncio
from collections import OrderedDict
import datetime
import gc
import json
import logging
import os
import threading
import time
import traceback
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from backend.schemas import AnalysisRequest
from backend.providers import get_provider_env_var

logger = logging.getLogger(__name__)

_ORPHAN_GRACE_SECONDS = 120.0
_COMPLETED_TTL_SECONDS = 300.0
_MAX_COMPLETED_SESSIONS = 8
_HEARTBEAT_INTERVAL_SECONDS = 4.0

_RUN_SESSIONS: "OrderedDict[str, AnalysisSession]" = OrderedDict()
_SESSIONS_LOCK = threading.Lock()


def _prune_sessions_locked(now: float) -> None:
    """Evict expired finished sessions to bound memory on constrained hosts."""
    expired = [
        rid
        for rid, sess in _RUN_SESSIONS.items()
        if sess.finished and sess.finished_at is not None and (now - sess.finished_at) > _COMPLETED_TTL_SECONDS
    ]
    for rid in expired:
        _RUN_SESSIONS.pop(rid, None)

    finished_ids = [rid for rid, sess in _RUN_SESSIONS.items() if sess.finished]
    while len(finished_ids) > _MAX_COMPLETED_SESSIONS:
        oldest = finished_ids.pop(0)
        _RUN_SESSIONS.pop(oldest, None)


def _get_session(run_id: str) -> "AnalysisSession | None":
    with _SESSIONS_LOCK:
        _prune_sessions_locked(time.time())
        return _RUN_SESSIONS.get(run_id)


def _get_or_create_session(run_id: str, resumable: bool) -> tuple["AnalysisSession", bool]:
    """Atomically fetch an existing session or register a new one. Returns (session, created)."""
    with _SESSIONS_LOCK:
        _prune_sessions_locked(time.time())
        existing = _RUN_SESSIONS.get(run_id)
        if existing is not None:
            return existing, False
        session = AnalysisSession(run_id, resumable=resumable)
        _RUN_SESSIONS[run_id] = session
        _RUN_SESSIONS.move_to_end(run_id)
        return session, True


def _remove_session(run_id: str) -> None:
    with _SESSIONS_LOCK:
        _RUN_SESSIONS.pop(run_id, None)


class AnalysisSession:
    """Event-loop-independent background execution session with replayable sequenced events."""

    def __init__(self, run_id: str, resumable: bool) -> None:
        self.run_id = run_id
        self.resumable = resumable
        self.orphan_grace_seconds = _ORPHAN_GRACE_SECONDS if resumable else 0.0
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._subscriber: tuple[asyncio.AbstractEventLoop, asyncio.Event] | None = None
        self.disconnected_at: float | None = None
        self.finished = False
        self.finished_at: float | None = None
        self.history: list[dict] = []
        self.last_stats: dict | None = None
        self.stats_ver = 0
        self.next_seq = 1
        self._started = False

    def start(self, req: AnalysisRequest) -> None:
        """Start background worker execution thread once for this session."""
        with self._lock:
            if self._started:
                return
            self._started = True
        worker = threading.Thread(target=self._run_worker, args=(req,), daemon=True)
        worker.start()
        if self.resumable:
            watchdog = threading.Thread(target=self._orphan_watchdog, daemon=True)
            watchdog.start()

    def set_subscriber(self, sub: tuple[asyncio.AbstractEventLoop, asyncio.Event]) -> None:
        """Attach the active WebSocket connection's (loop, event) notifier."""
        with self._lock:
            self._subscriber = sub
            self.disconnected_at = None

    def clear_subscriber(self, sub: tuple[asyncio.AbstractEventLoop, asyncio.Event]) -> None:
        """Detach only if `sub` is still the current subscriber (avoids stale close races)."""
        with self._lock:
            if self._subscriber is sub:
                self._subscriber = None
                if not self.finished and self.disconnected_at is None:
                    self.disconnected_at = time.time()
                if not self.resumable and not self.finished:
                    self._cancel_locked()

    def _wake_subscriber_locked(self) -> None:
        sub = self._subscriber
        if sub is None:
            return
        loop, evt = sub
        try:
            loop.call_soon_threadsafe(evt.set)
        except RuntimeError:
            # Subscriber's loop already closed
            self._subscriber = None
            if not self.finished and self.disconnected_at is None:
                self.disconnected_at = time.time()

    def _cancel_locked(self) -> None:
        self.cancel_event.set()
        self.finished = True
        if self.finished_at is None:
            self.finished_at = time.time()
        self._wake_subscriber_locked()

    def cancel(self) -> None:
        """Explicitly cancel an in-progress run (user clicked Back to Setup or ephemeral drop)."""
        with self._lock:
            self._cancel_locked()

    def _publish(self, msg_type: str, payload: dict) -> None:
        """Record a sequenced event or latest stats snapshot and wake the active WebSocket."""
        with self._lock:
            if msg_type == "stats":
                self.stats_ver += 1
                self.last_stats = {"type": "stats", "data": payload}
            else:
                seq = self.next_seq
                self.next_seq += 1
                self.history.append({"type": msg_type, "data": payload, "seq": seq})

            if msg_type in ("complete", "error"):
                self.finished = True
                if self.finished_at is None:
                    self.finished_at = time.time()

            self._wake_subscriber_locked()

    def snapshot_pending(self, after_seq: int, last_stats_ver: int) -> tuple[list[dict], dict | None, int, bool]:
        """Return (frames with seq > after_seq, updated stats or None, stats_ver, finished)."""
        with self._lock:
            frames = [frame for frame in self.history if frame["seq"] > after_seq]
            stats_frame = self.last_stats if (self.stats_ver > last_stats_ver and self.last_stats is not None) else None
            return frames, stats_frame, self.stats_ver, self.finished

    def _orphan_watchdog(self) -> None:
        """Cancel resumable runs if client stays disconnected beyond the reconnect grace window."""
        while not self.cancel_event.wait(5.0):
            with self._lock:
                if self.finished:
                    return
                if (
                    self._subscriber is None
                    and self.disconnected_at is not None
                    and (time.time() - self.disconnected_at) >= self.orphan_grace_seconds
                ):
                    logger.info(
                        "Run %s orphaned past %.0fs without reconnect; cancelling worker",
                        self.run_id,
                        self.orphan_grace_seconds,
                    )
                    self.cancel_event.set()
                    return

    def _run_worker(self, req: AnalysisRequest) -> None:
        """Execute graph compilation, streaming, rating, and reporting cleanly off the event loop."""
        graph = None
        report_sections: dict = {}
        final_state: dict = {}
        seen_msg_ids: set = set()
        try:
            env_var = get_provider_env_var(req.llm_provider)
            if env_var and req.api_key:
                os.environ[env_var] = req.api_key

            self._publish("status", {
                "message": f"Initializing analysis for {req.ticker}...",
                "phase": "init",
            })

            from tradingagents.default_config import DEFAULT_CONFIG

            depth_key = (req.research_depth or "shallow").strip().lower()
            if depth_key == "deep":
                max_debate_rounds = 2
                max_risk_rounds = 2
                max_tool_rounds = 4
            elif depth_key == "medium":
                max_debate_rounds = 1
                max_risk_rounds = 2
                max_tool_rounds = 3
            else:
                max_debate_rounds = 1
                max_risk_rounds = 1
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
            config["llm_max_retries"] = 2
            config["llm_timeout"] = 60

            if req.openai_reasoning_effort:
                config["openai_reasoning_effort"] = req.openai_reasoning_effort
            if req.google_thinking_level:
                config["google_thinking_level"] = req.google_thinking_level
            if req.anthropic_effort:
                config["anthropic_effort"] = req.anthropic_effort

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

            crypto_suffixes = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
            ticker = req.ticker.strip().upper()
            asset_type = "crypto" if ticker.endswith(crypto_suffixes) else "stock"
            analysis_date = req.analysis_date or datetime.date.today().isoformat()

            try:
                from tradingagents.graph.trading_graph import TradingAgentsGraph
                from backend.stats_handler import StatsCallbackHandler

                stats_handler = StatsCallbackHandler()
                graph = TradingAgentsGraph(
                    selected_analysts=selected_analysts,
                    config=config,
                    debug=False,
                    callbacks=[stats_handler],
                )
            except Exception as e:
                self._publish("error", {
                    "message": f"Failed to initialize graph: {e}",
                    "trace": traceback.format_exc(),
                })
                return

            if self.cancel_event.is_set():
                return

            self._publish("status", {
                "message": "Graph compiled. Starting analysis...",
                "phase": "running",
            })

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
                self._publish("agent_update", {
                    "agent": agent_display_map.get(key, key),
                    "status": "in_progress",
                })

            start_time = time.time()
            init_state = graph.create_run_state(ticker, analysis_date, asset_type)
            if self.cancel_event.is_set():
                return

            args = graph.propagator.get_graph_args(callbacks=[stats_handler])
            args["stream_mode"] = ["values", "tasks"]
            args["subgraphs"] = True
            if "config" not in args or not args["config"]:
                args["config"] = {}
            if "recursion_limit" not in args["config"]:
                args["config"]["recursion_limit"] = int(
                    config.get("max_recur_limit", getattr(graph.propagator, "max_recur_limit", 100))
                )

            from tradingagents.dataflows.config import run_config_context
            context = run_config_context(config)

            last_debate_speech = None
            last_risk_key = None
            research_mgr_started = False
            portfolio_mgr_started = False
            stop_stats = threading.Event()

            def _stats_ticker() -> None:
                while not stop_stats.wait(1.0):
                    if self.cancel_event.is_set():
                        return
                    for warn_msg in stats_handler.pop_warnings():
                        self._publish("message", {
                            "sender": "System",
                            "content": warn_msg,
                            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                        })
                    s = stats_handler.get_stats()
                    self._publish("stats", {
                        "llm_calls": s["llm_calls"],
                        "tool_calls": s["tool_calls"],
                        "tokens": {"input": s["tokens_in"], "output": s["tokens_out"]},
                        "elapsed": round(time.time() - start_time, 1),
                    })

            stats_thread = threading.Thread(target=_stats_ticker, daemon=True)
            stats_thread.start()

            def _flush_warnings() -> None:
                for warn_msg in stats_handler.pop_warnings():
                    self._publish("message", {
                        "sender": "System",
                        "content": warn_msg,
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    })

            try:
                stream = context.run(graph.graph.stream, init_state, **args)
                try:
                    while not self.cancel_event.is_set():
                        step = context.run(next, stream, None)
                        _flush_warnings()
                        if step is None or self.cancel_event.is_set():
                            break

                        namespace, mode, chunk = step
                        now_ts = datetime.datetime.now().strftime("%H:%M:%S")

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

                                sub_msgs = result.get("messages", [])
                                if isinstance(sub_msgs, list):
                                    for msg in sub_msgs:
                                        raw_id = getattr(msg, "id", None)
                                        msg_key = raw_id or hash((type(msg).__name__, str(getattr(msg, "content", ""))))
                                        if msg_key in seen_msg_ids:
                                            continue
                                        seen_msg_ids.add(msg_key)

                                        for tc in getattr(msg, "tool_calls", None) or []:
                                            self._publish("tool_call", {
                                                "tool": tc.get("name", "tool"),
                                                "args": tc.get("args", {}),
                                                "timestamp": now_ts,
                                            })

                                        if msg.__class__.__name__ == "ToolMessage":
                                            tool_name = getattr(msg, "name", "Tool")
                                            content_str = _extract_text(msg.content)
                                            self._publish("message", {
                                                "sender": f"{tool_name} (Tool)",
                                                "content": (content_str[:300] + "...") if len(content_str) > 300 else content_str,
                                                "timestamp": now_ts,
                                            })
                                        else:
                                            content = _extract_text(getattr(msg, "content", ""))
                                            if content.strip():
                                                self._publish("message", {
                                                    "sender": analyst_name,
                                                    "content": (content[:400] + "...") if len(content) > 400 else content,
                                                    "timestamp": now_ts,
                                                })

                                for r_key, a_name in [
                                    ("market_report", "Market Analyst"),
                                    ("sentiment_report", "Sentiment Analyst"),
                                    ("news_report", "News Analyst"),
                                    ("fundamentals_report", "Fundamentals Analyst"),
                                ]:
                                    if result.get(r_key) and r_key not in report_sections:
                                        report_sections[r_key] = result[r_key]
                                        final_state[r_key] = result[r_key]
                                        self._publish("report_section", {"section": r_key, "content": result[r_key]})
                                        self._publish("agent_update", {"agent": a_name, "status": "completed"})
                                        self._publish("message", {
                                            "sender": a_name,
                                            "content": f"Completed {a_name} report.",
                                            "timestamp": now_ts,
                                        })

                        elif mode == "values" and isinstance(chunk, dict):
                            for k, v in chunk.items():
                                if k != "messages":
                                    final_state[k] = v

                            if chunk.get("investment_debate_state"):
                                ds = chunk["investment_debate_state"]
                                current_resp = ds.get("current_response", "")
                                debate_count = int(ds.get("count", 0) or 0)
                                max_debate_allowed = 2 * max_debate_rounds

                                if current_resp and current_resp != last_debate_speech and "investment_plan" not in report_sections:
                                    last_debate_speech = current_resp
                                    speaker = "Bull Researcher" if current_resp.startswith("Bull") else "Bear Researcher"
                                    speech_text = current_resp.split(":", 1)[1].strip() if ":" in current_resp else current_resp
                                    self._publish("message", {
                                        "sender": speaker,
                                        "content": (speech_text[:400] + "...") if len(speech_text) > 400 else speech_text,
                                        "timestamp": now_ts,
                                    })

                                    if debate_count >= max_debate_allowed and not research_mgr_started:
                                        research_mgr_started = True
                                        self._publish("agent_update", {"agent": "Bull Researcher", "status": "completed"})
                                        self._publish("agent_update", {"agent": "Bear Researcher", "status": "completed"})
                                        self._publish("agent_update", {"agent": "Research Manager", "status": "in_progress"})
                                        self._publish("message", {
                                            "sender": "Research Manager",
                                            "content": "Investment debate complete. Synthesizing investment plan...",
                                            "timestamp": now_ts,
                                        })
                                    elif debate_count < max_debate_allowed:
                                        next_debater = "Bear Researcher" if speaker == "Bull Researcher" else "Bull Researcher"
                                        self._publish("agent_update", {"agent": speaker, "status": "completed"})
                                        self._publish("agent_update", {"agent": next_debater, "status": "in_progress"})

                                if ds.get("bull_history") and report_sections.get("bull_research") != ds["bull_history"]:
                                    report_sections["bull_research"] = ds["bull_history"]
                                    self._publish("report_section", {"section": "bull_research", "content": ds["bull_history"]})

                                if ds.get("bear_history") and report_sections.get("bear_research") != ds["bear_history"]:
                                    report_sections["bear_research"] = ds["bear_history"]
                                    self._publish("report_section", {"section": "bear_research", "content": ds["bear_history"]})

                            if chunk.get("investment_plan") and "investment_plan" not in report_sections:
                                report_sections["investment_plan"] = chunk["investment_plan"]
                                self._publish("report_section", {"section": "investment_plan", "content": chunk["investment_plan"]})
                                self._publish("agent_update", {"agent": "Bull Researcher", "status": "completed"})
                                self._publish("agent_update", {"agent": "Bear Researcher", "status": "completed"})
                                self._publish("agent_update", {"agent": "Research Manager", "status": "completed"})
                                self._publish("message", {
                                    "sender": "Research Manager",
                                    "content": "Investment plan finalized.",
                                    "timestamp": now_ts,
                                })
                                self._publish("agent_update", {"agent": "Trader", "status": "in_progress"})

                            if chunk.get("trader_investment_plan") and "trader_plan" not in report_sections:
                                report_sections["trader_plan"] = chunk["trader_investment_plan"]
                                self._publish("report_section", {"section": "trader_plan", "content": chunk["trader_investment_plan"]})
                                self._publish("agent_update", {"agent": "Trader", "status": "completed"})
                                self._publish("message", {
                                    "sender": "Trader",
                                    "content": "Trading plan formulated.",
                                    "timestamp": now_ts,
                                })
                                self._publish("agent_update", {"agent": "Aggressive Analyst", "status": "in_progress"})

                            if chunk.get("risk_debate_state") and "final_decision" not in report_sections:
                                rs = chunk["risk_debate_state"]
                                raw_speaker = rs.get("latest_speaker")
                                risk_count = int(rs.get("count", 0) or 0)
                                max_risk_allowed = 3 * max_risk_rounds
                                history = rs.get("history", "")

                                turn_key = (risk_count, raw_speaker, hash(history))
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
                                        self._publish("message", {
                                            "sender": mapped_speaker,
                                            "content": (txt[:400] + "...") if len(txt) > 400 else txt,
                                            "timestamp": now_ts,
                                        })

                                    if risk_count >= max_risk_allowed:
                                        for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
                                            self._publish("agent_update", {"agent": agent, "status": "completed"})
                                        if not portfolio_mgr_started:
                                            portfolio_mgr_started = True
                                            self._publish("agent_update", {"agent": "Portfolio Manager", "status": "in_progress"})
                                            self._publish("message", {
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
                                        self._publish("agent_update", {"agent": mapped_speaker, "status": "completed"})
                                        next_speaker = next_map.get(mapped_speaker)
                                        if next_speaker:
                                            self._publish("agent_update", {"agent": next_speaker, "status": "in_progress"})

                            if chunk.get("final_trade_decision") and "final_decision" not in report_sections:
                                report_sections["final_decision"] = chunk["final_trade_decision"]
                                self._publish("report_section", {"section": "final_decision", "content": chunk["final_trade_decision"]})
                                for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"):
                                    self._publish("agent_update", {"agent": agent, "status": "completed"})
                                self._publish("message", {
                                    "sender": "Portfolio Manager",
                                    "content": "Final risk evaluation complete and decision signed off.",
                                    "timestamp": now_ts,
                                })
                finally:
                    context.run(stream.close)
            except Exception as exc:
                if not self.cancel_event.is_set():
                    tb = traceback.format_exc()
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
                            f"Agentic Loop Detected: An agent failed to resolve a task and hit the maximum step limit ({rec_limit}). "
                            "Analysis halted to prevent server crash."
                        )
                    self._publish("error", {"message": err_msg, "trace": tb})
                return
            finally:
                stop_stats.set()

            _flush_warnings()

            if self.cancel_event.is_set():
                logger.info("Run %s cancelled; skipping final assembly", self.run_id)
                return

            from tradingagents.agents.rating import run_rating
            rating = run_rating(final_state) if final_state else "REVIEW"

            try:
                graph.record_decision(ticker, analysis_date, final_state)
            except Exception as rec_err:
                logger.warning(f"Failed to record decision: {rec_err}")

            saved_report_path = None
            if hasattr(graph, "save_reports"):
                try:
                    saved_report_path = str(graph.save_reports(final_state, ticker))
                    logger.info(f"Successfully saved analysis reports to {saved_report_path}")
                except Exception as rep_err:
                    logger.warning(f"Failed to save reports to disk: {rep_err}")

            elapsed = time.time() - start_time
            s = stats_handler.get_stats()
            self._publish("stats", {
                "llm_calls": s["llm_calls"],
                "tool_calls": s["tool_calls"],
                "tokens": {"input": s["tokens_in"], "output": s["tokens_out"]},
                "elapsed": round(elapsed, 1),
            })

            complete_report = _build_complete_report(final_state, report_sections)

            self._publish("complete", {
                "rating": rating,
                "report": complete_report,
                "report_path": saved_report_path,
                "sections": dict(report_sections),
            })

        except Exception as e:
            logger.exception("Analysis execution error")
            self._publish("error", {
                "message": f"Execution error: {e}",
                "trace": traceback.format_exc(),
            })
        finally:
            with self._lock:
                self.finished = True
                if self.finished_at is None:
                    self.finished_at = time.time()
                self._wake_subscriber_locked()
            seen_msg_ids.clear()
            final_state.clear()
            report_sections.clear()
            graph = None
            if not self.resumable:
                _remove_session(self.run_id)
            gc.collect()


async def _serve_connection(ws: WebSocket, session: AnalysisSession, last_seq: int) -> None:
    """Stream sequenced session updates and proxy heartbeats over `ws` until terminal or disconnect."""
    loop = asyncio.get_running_loop()
    notify_event = asyncio.Event()
    send_lock = asyncio.Lock()
    client_closed = asyncio.Event()
    sub = (loop, notify_event)

    session.set_subscriber(sub)
    drain_task = asyncio.create_task(_drain_client_messages(ws, session, send_lock, client_closed))

    sent_seq = last_seq
    sent_stats_ver = -1

    try:
        while not client_closed.is_set() and not session.cancel_event.is_set():
            notify_event.clear()
            frames, stats_frame, new_stats_ver, is_finished = session.snapshot_pending(sent_seq, sent_stats_ver)

            if stats_frame is not None:
                async with send_lock:
                    await ws.send_json(stats_frame)
                sent_stats_ver = new_stats_ver

            for frame in frames:
                async with send_lock:
                    await ws.send_json(frame)
                sent_seq = frame["seq"]

            if is_finished:
                break

            try:
                await asyncio.wait_for(notify_event.wait(), timeout=_HEARTBEAT_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                async with send_lock:
                    await ws.send_json({
                        "type": "status",
                        "data": {"message": "Analysis running...", "phase": "running", "heartbeat": True},
                    })
    except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
        pass
    except Exception:
        logger.debug("WebSocket connection closed while pumping events", exc_info=True)
    finally:
        session.clear_subscriber(sub)
        if not drain_task.done():
            drain_task.cancel()
            await asyncio.gather(drain_task, return_exceptions=True)


async def websocket_analysis_route(websocket: WebSocket):
    """Handle a WebSocket connection for starting or resuming a TradingAgents analysis run.

    Protocol:
    1. Client connects and sends either:
       - an AnalysisRequest JSON payload (optionally carrying `run_id` for reconnect resume), or
       - `{"action": "resume", "run_id": "...", "last_seq": <int>}` after a proxy drop.
    2. Server streams sequenced JSON events (`status`, `agent_update`, `tool_call`, `message`,
       `report_section`, `stats`, `complete`, `error`) and responds to `ping` with `pong`.
    """
    await websocket.accept()

    try:
        data = await websocket.receive_text()
        try:
            payload = json.loads(data)
        except Exception as e:
            await _send(websocket, "error", {"message": f"Invalid configuration: {e}"})
            return

        if not isinstance(payload, dict):
            await _send(websocket, "error", {"message": "Invalid configuration: JSON object expected"})
            return

        if payload.get("action") == "resume":
            run_id = str(payload.get("run_id") or "")
            last_seq = int(payload.get("last_seq") or 0)
            session = _get_session(run_id) if run_id else None
            if session is None:
                await _send(
                    websocket,
                    "error",
                    {
                        "message": (
                            "Analysis session expired on the server (container restarted or timed out). "
                            "Please return to Setup and start again."
                        )
                    },
                )
                return
            await _serve_connection(websocket, session, last_seq)
            return

        try:
            req = AnalysisRequest(**payload)
        except Exception as e:
            await _send(websocket, "error", {"message": f"Invalid configuration: {e}"})
            return

        if req.run_id:
            session, created = _get_or_create_session(req.run_id, resumable=True)
            if created:
                session.start(req)
        else:
            session, _ = _get_or_create_session(uuid.uuid4().hex, resumable=False)
            session.start(req)

        await _serve_connection(websocket, session, last_seq=0)

    except WebSocketDisconnect:
        logger.info("Client disconnected during analysis")
    except Exception as e:
        logger.exception("Unexpected WebSocket error")
        await _send(websocket, "error", {"message": f"Internal error: {e}"})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _drain_client_messages(
    ws: WebSocket,
    session: AnalysisSession,
    send_lock: asyncio.Lock,
    client_closed: asyncio.Event,
) -> None:
    """Continuously read incoming frames so Uvicorn stays unpaused and ping/cancel frames are handled."""
    try:
        while not session.cancel_event.is_set() and not session.finished:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            if text:
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict):
                        msg_type = payload.get("type")
                        if msg_type == "ping":
                            async with send_lock:
                                await ws.send_json({"type": "pong", "data": {}})
                        elif msg_type == "cancel":
                            session.cancel()
                            break
                except json.JSONDecodeError:
                    pass
    except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
        pass
    except Exception:
        pass
    finally:
        client_closed.set()
        with session._lock:
            session._wake_subscriber_locked()


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
