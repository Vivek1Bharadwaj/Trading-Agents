import re
import warnings
from abc import ABC, abstractmethod
from typing import Any

_RETRY_DELAY_RE = re.compile(r"retry\s+in\s+(?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s|retryDelay['\":\s]+(\d+)s", re.IGNORECASE)


class FatalLLMError(RuntimeError):
    """Non-retryable LLM failure (invalid key, retired/unknown model, or daily quota exhaustion)."""


def classify_fatal_llm_error(exc: BaseException) -> str | None:
    """Return an actionable message if ``exc`` cannot recover via fallback/retries, else None."""
    if isinstance(exc, FatalLLMError):
        return str(exc)

    msg = str(exc or "")
    low = msg.lower()

    if "404" in msg and ("not_found" in low or "not found" in low or "no longer available" in low or "does not exist" in low):
        return (
            "Selected model was rejected by the provider (404 NOT_FOUND — unavailable or retired). "
            "Open Setup Step 6 and choose an active model (for Google Gemini, select gemini-3.8-flash or gemini-3.5-flash-lite)."
        )

    if any(tok in low for tok in ("api_key_invalid", "invalid_api_key", "invalid api key", "incorrect api key", "authenticationerror", "permission_denied")) or (
        ("401" in msg or "403" in msg) and any(tok in low for tok in ("unauthorized", "forbidden", "api key", "permission", "invalid"))
    ):
        return "Provider authentication failed (401/403). Verify your API key and permissions in Setup."

    if "resource_exhausted" in low or "429" in msg:
        is_daily = any(tok in low for tok in ("requestsperday", "perday", "per day", "daily limit"))
        m = _RETRY_DELAY_RE.search(msg)
        retry_seconds = 0.0
        if m:
            if m.group(4):
                retry_seconds = float(m.group(4))
            else:
                hrs = float(m.group(1) or 0)
                mins = float(m.group(2) or 0)
                secs = float(m.group(3) or 0)
                retry_seconds = hrs * 3600 + mins * 60 + secs
        if is_daily or retry_seconds > 120:
            return (
                "Daily free-tier API quota exhausted (429 RESOURCE_EXHAUSTED). "
                "Switch to another model (such as gemini-3.5-flash-lite or another provider), reduce analyst count/depth, "
                "or wait for the daily quota reset."
            )

    return None


def raise_if_fatal_llm_error(exc: BaseException) -> None:
    """Re-raise ``exc`` as FatalLLMError when retries/fallback cannot recover."""
    fatal = classify_fatal_llm_error(exc)
    if fatal:
        raise FatalLLMError(fatal) from exc


def normalize_content(response):
    """Normalize LLM response content to a plain string.

    Multiple providers (OpenAI Responses API, Google Gemini 3) return content
    as a list of typed blocks, e.g. [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}].
    Downstream agents expect response.content to be a string. This extracts
    and joins the text blocks, discarding reasoning/metadata blocks.
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """Return the provider name used in warning messages."""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """Warn when the model is outside the known list for the provider."""
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        pass
