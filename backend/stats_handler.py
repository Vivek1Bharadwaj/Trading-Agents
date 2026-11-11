import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult


class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self._warnings: list[str] = []
        self._last_warn_msg = ""

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Record transient provider errors so the UI live feed reflects retries."""
        from tradingagents.llm_clients.base_client import classify_fatal_llm_error

        if classify_fatal_llm_error(error):
            return
        err_str = str(error or "")
        low = err_str.lower()
        if "429" in err_str or "resource_exhausted" in low:
            notice = "Provider rate limit (429) hit — retrying briefly..."
        elif "503" in err_str or "unavailable" in low:
            notice = "Provider experiencing high demand (503) — retrying briefly..."
        else:
            notice = f"Temporary LLM call issue ({type(error).__name__}); retrying/falling back..."
        with self._lock:
            if notice != self._last_warn_msg or len(self._warnings) == 0:
                self._last_warn_msg = notice
                self._warnings.append(notice)

    def pop_warnings(self) -> list[str]:
        """Drain queued transient warnings for the WebSocket stream."""
        with self._lock:
            items = list(self._warnings)
            self._warnings.clear()
            return items

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when an LLM starts."""
        with self._lock:
            self.llm_calls += 1

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when a chat model starts."""
        with self._lock:
            self.llm_calls += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from LLM response."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            generation = None

        usage_metadata = None
        if generation and hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        if usage_metadata:
            with self._lock:
                self.tokens_in += usage_metadata.get("input_tokens", 0)
                self.tokens_out += usage_metadata.get("output_tokens", 0)
        elif response.llm_output and "token_usage" in response.llm_output:
            tu = response.llm_output["token_usage"]
            with self._lock:
                self.tokens_in += tu.get("prompt_tokens", 0) or tu.get("input_tokens", 0)
                self.tokens_out += tu.get("completion_tokens", 0) or tu.get("output_tokens", 0)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Increment tool call counter when a tool starts."""
        with self._lock:
            self.tool_calls += 1

    def get_stats(self) -> dict[str, Any]:
        """Return current statistics."""
        with self._lock:
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
            }
