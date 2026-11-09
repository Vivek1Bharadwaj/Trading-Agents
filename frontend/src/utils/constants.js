export const LANGUAGES = [
  "English", "Chinese (中文)", "Japanese (日本語)", "Korean (한국어)", 
  "Hindi (हिन्दी)", "Spanish (Español)", "Portuguese (Português)", 
  "French (Français)", "German (Deutsch)", "Arabic (العربية)", 
  "Russian (Русский)", "Custom"
];

export const ANALYSTS = [
  { id: "Market Analyst", label: "Market Analyst" },
  { id: "Sentiment Analyst", label: "Sentiment Analyst" },
  { id: "News Analyst", label: "News Analyst" },
  { id: "Fundamentals Analyst", label: "Fundamentals Analyst" }
];

export const DEPTH_OPTIONS = [
  { id: "shallow", label: "Shallow", desc: "Quick research, few debate rounds (1 round)" },
  { id: "medium", label: "Medium", desc: "Moderate research, balanced debate (3 rounds)" },
  { id: "deep", label: "Deep", desc: "Comprehensive research, thorough debate (5 rounds)" }
];

export const PROVIDERS = [
  {"display": "OpenAI", "key": "openai", "url": "https://api.openai.com/v1", "env_var": "OPENAI_API_KEY"},
  {"display": "Google", "key": "google", "url": null, "env_var": "GOOGLE_API_KEY"},
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
  {"display": "Azure OpenAI", "key": "azure", "url": null, "env_var": "AZURE_OPENAI_API_KEY"},
  {"display": "Amazon Bedrock", "key": "bedrock", "url": null, "env_var": null},
  {"display": "Ollama", "key": "ollama", "url": "http://localhost:11434/v1", "env_var": null},
  {"display": "OpenAI-compatible", "key": "openai_compatible", "url": null, "env_var": "OPENAI_API_KEY"}
];
