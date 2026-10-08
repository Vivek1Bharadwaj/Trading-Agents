"""Provider registry and model catalog for the API layer."""

from typing import List, Optional

from backend.schemas import ProviderInfo

# Import model catalog from the tradingagents package
try:
    from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
except ImportError:
    MODEL_OPTIONS = {}

# Complete provider registry with display names, keys, default URLs, and env vars
PROVIDERS = [
    {"display": "OpenAI", "key": "openai", "url": "https://api.openai.com/v1", "env_var": "OPENAI_API_KEY"},
    {"display": "Google", "key": "google", "url": None, "env_var": "GOOGLE_API_KEY"},
    {"display": "Anthropic", "key": "anthropic", "url": "https://api.anthropic.com/", "env_var": "ANTHROPIC_API_KEY"},
    {"display": "xAI", "key": "xai", "url": "https://api.x.ai/v1", "env_var": "XAI_API_KEY"},
    {"display": "DeepSeek", "key": "deepseek", "url": "https://api.deepseek.com", "env_var": "DEEPSEEK_API_KEY"},
    {"display": "Qwen (International)", "key": "qwen", "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "env_var": "DASHSCOPE_API_KEY"},
    {"display": "Qwen (China)", "key": "qwen-cn", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "env_var": "DASHSCOPE_CN_API_KEY"},
    {"display": "GLM (Z.AI)", "key": "glm", "url": "https://api.z.ai/api/paas/v4/", "env_var": "ZHIPU_API_KEY"},
    {"display": "GLM (BigModel China)", "key": "glm-cn", "url": "https://open.bigmodel.cn/api/paas/v4/", "env_var": "ZHIPU_CN_API_KEY"},
    {"display": "MiniMax (Global)", "key": "minimax", "url": "https://api.minimax.io/v1", "env_var": "MINIMAX_API_KEY"},
    {"display": "MiniMax (China)", "key": "minimax-cn", "url": "https://api.minimaxi.com/v1", "env_var": "MINIMAX_CN_API_KEY"},
    {"display": "OpenRouter", "key": "openrouter", "url": "https://openrouter.ai/api/v1", "env_var": "OPENROUTER_API_KEY"},
    {"display": "Mistral", "key": "mistral", "url": "https://api.mistral.ai/v1", "env_var": "MISTRAL_API_KEY"},
    {"display": "Kimi (Moonshot)", "key": "kimi", "url": "https://api.moonshot.ai/v1", "env_var": "MOONSHOT_API_KEY"},
    {"display": "Groq", "key": "groq", "url": "https://api.groq.com/openai/v1", "env_var": "GROQ_API_KEY"},
    {"display": "NVIDIA NIM", "key": "nvidia", "url": "https://integrate.api.nvidia.com/v1", "env_var": "NVIDIA_API_KEY"},
    {"display": "Azure OpenAI", "key": "azure", "url": None, "env_var": "AZURE_OPENAI_API_KEY"},
    {"display": "Amazon Bedrock", "key": "bedrock", "url": None, "env_var": None},
    {"display": "Ollama", "key": "ollama", "url": "http://localhost:11434/v1", "env_var": None},
    {"display": "OpenAI-compatible", "key": "openai_compatible", "url": None, "env_var": "OPENAI_API_KEY"},
]


def get_providers() -> List[ProviderInfo]:
    """Return all supported providers."""
    return [ProviderInfo(**p) for p in PROVIDERS]


def get_models_for_provider(provider_key: str) -> dict:
    """Return quick and deep model options for a provider.

    MODEL_OPTIONS stores tuples of (display_name, model_id). We return
    them as lists of {display, value} objects for the frontend dropdowns.
    """
    models = MODEL_OPTIONS.get(provider_key.lower(), {})

    def _format(options):
        return [{"display": display, "value": value} for display, value in options]

    return {
        "quick": _format(models.get("quick", [])),
        "deep": _format(models.get("deep", [])),
    }


def get_provider_env_var(provider_key: str) -> Optional[str]:
    """Return the environment variable name for a provider's API key."""
    for p in PROVIDERS:
        if p["key"] == provider_key:
            return p.get("env_var")
    return None


def get_provider_url(provider_key: str) -> Optional[str]:
    """Return the default backend URL for a provider."""
    for p in PROVIDERS:
        if p["key"] == provider_key:
            return p.get("url")
    return None
