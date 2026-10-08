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
  "OpenAI", "Google", "Anthropic", "xAI", "DeepSeek", "Qwen (International)", 
  "Qwen (China)", "GLM (Z.AI)", "GLM (BigModel China)", "MiniMax (Global)", 
  "MiniMax (China)", "OpenRouter", "Mistral", "Kimi (Moonshot)", "Groq", 
  "NVIDIA NIM", "Azure OpenAI", "Amazon Bedrock", "Ollama", "OpenAI-compatible"
];
