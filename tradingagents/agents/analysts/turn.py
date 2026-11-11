"""One turn of a tool-using analyst, and its last turn once its tool rounds are spent."""

import json
import logging
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.llm_clients.base_client import raise_if_fatal_llm_error

logger = logging.getLogger(__name__)

WRAP_UP = (
    "You have used every tool round this report allows. Write your final report "
    "now from the tool results above, and say which data you could not retrieve."
)


def _normalize_str(content) -> str:
    """Ensure message content is always converted to a clean string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts) if parts else str(content)
    return str(content or "")


def take_turn(prompt, llm, tools, messages):
    """The analyst's reply and its report, which stays empty while it calls tools.

    Told to wrap up, it answers without tools: a model offered tools may call one
    whatever it is told. Its earlier calls and their results reach it as text,
    since a provider may refuse a history holding tool calls when none are bound.
    """
    try:
        if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == WRAP_UP:
            prompt = prompt.partial(tool_names="none; your tool rounds are spent")
            result = (prompt | llm).invoke(_as_text(messages))
            return result, _normalize_str(result.content)

        result = (prompt | llm.bind_tools(tools)).invoke(messages)
        return result, "" if getattr(result, "tool_calls", None) else _normalize_str(result.content)
    except Exception as exc:
        raise_if_fatal_llm_error(exc)
        logger.error("LLM error in analyst turn: %s", exc)
        fallback_content = f"Analysis report generated from available data. (Note: LLM encountered temporary error: {exc})"
        fallback_result = AIMessage(content=fallback_content)
        return fallback_result, fallback_content


def _as_text(messages):
    """The history with its tool calls and tool results written out as plain messages."""
    written = []
    for message in messages:
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
            said = message.content if isinstance(message.content, str) else ""
            calls = "; ".join(f"{c['name']}({json.dumps(c['args'], default=str)})" for c in message.tool_calls)
            written.append(AIMessage(content=f"{said}\n[Called {calls}]".strip()))
        elif isinstance(message, ToolMessage):
            written.append(HumanMessage(content=f"[{message.name or 'Tool'} returned]\n{message.content}"))
        else:
            written.append(message)
    return written
