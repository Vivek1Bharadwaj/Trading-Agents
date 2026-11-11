# Trading-Agents 📈

**Trading-Agents** is a modern, full-stack multi-agent LLM financial trading framework. It coordinates teams of specialized AI agents—spanning market data analysis, news evaluation, sentiment tracking, fundamental research, bull/bear investment debates, and risk management—to generate comprehensive, actionable investment reports.

Developed and maintained by **[Vivek Bharadwaj](https://github.com/Vivek1Bharadwaj)**.

---

## 🌟 Highlights & Architecture

- **Multi-Agent Deliberation Pipeline**:
  - **Analyst Team**: Market Analyst, Sentiment Analyst, News Analyst, and Fundamentals Analyst run in parallel with exception-safe data tools.
  - **Research Team**: Bull Researcher and Bear Researcher engage in adversarial debate managed by the Research Manager.
  - **Trading Team**: Formulates trade execution plans based on synthesized research.
  - **Risk Management**: Aggressive, Conservative, and Neutral analysts evaluate portfolio downside and calibrate position limits.
  - **Portfolio Manager**: Final decision arbiter delivering clear signals (`BUY`, `HOLD`, `SELL`, `OVERWEIGHT`, `UNDERWEIGHT`).
- **Resilient & Cloud-Optimized Architecture**:
  - **Loop-of-Death Protection**: All financial tools catch exceptions internally, return natural language failure sentinels, and instruct agents not to retry, preventing runaway API request spam.
  - **Memory & Token Optimization**: Large financial reports and debate histories are automatically bounded to prevent token explosion and silent Out-Of-Memory (OOM) crashes on constrained hosts (e.g. Render 512MB free tier).
  - **WebSocket Keep-Alive Tunneling**: Continuous background heartbeats and throttled telemetry updates prevent proxies and cloud hosts from dropping connections.
  - **Rate Limit Circuit Breakers**: Built-in exponential backoff retries (3 to 5 attempts) to ride out bursty `429 Too Many Requests` rate limits.
- **Web-First Interface**: Real-time interactive UI with WebSocket-streamed logs, per-agent live pipeline state, and live report previews.
- **Finanix Design System**: High-contrast, accessibility-focused (WCAG 2.2 AA compliant) dark theme with custom typography and clean visual metrics.
- **Provider Agnostic**: Out-of-the-box support for OpenAI, Google Gemini, Anthropic Claude, DeepSeek, Groq, Ollama, OpenRouter, and OpenAI-compatible endpoints.

---

## 🚀 Quick Start (Running on Localhost)

### 1. Prerequisites
- **Python**: 3.11 or higher
- **Node.js**: 18+ (Node 20+ recommended) & npm

---

### 2. Clone the Repository
```bash
git clone https://github.com/Vivek1Bharadwaj/Trading-Agents.git
cd Trading-Agents
```

---

### 3. Build the React Frontend
Because FastAPI serves the compiled web interface directly from `frontend/dist/`, build the frontend bundle first:

**On Windows (PowerShell):**
```powershell
cd frontend
npm install
npm run build
cd ..
```

**On Linux / macOS:**
```bash
cd frontend
npm install
npm run build
cd ..
```

---

### 4. Create & Activate a Python Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or invoke `.\.venv\Scripts\python.exe` directly).*

**On Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 5. Install Backend Dependencies
```bash
pip install -r requirements.txt
```

*(Optional: If you plan to use Amazon Bedrock, install the AWS dependencies via `pip install ".[bedrock]"`).*

---

### 6. Configure Environment Variables (Optional)
You can provide your LLM API keys directly in the Web UI Setup Wizard at runtime, or create a `.env` file in the project root:

```env
# Primary LLM API Keys (set at least one):
OPENAI_API_KEY=your_openai_key_here
GOOGLE_API_KEY=your_google_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here

# Optional Alternative Providers:
DEEPSEEK_API_KEY=your_deepseek_key_here
GROQ_API_KEY=your_groq_key_here
OPENROUTER_API_KEY=your_openrouter_key_here

# Optional Macro & Filings Data:
FRED_API_KEY=your_fred_key_here
SEC_EDGAR_USER_AGENT="YourName your_email@example.com"
```
*(Note: For local **Ollama**, no API key is required; it connects to `http://localhost:11434/v1` automatically).*

---

### 7. Run the Application
From the repository root (`Trading-Agents`):

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

You can verify the backend health status at `http://localhost:8000/api/health`.

---

## 🛠️ Frontend Development Mode (Hot-Reload)

If you are developing or modifying the React UI in `frontend/src`:

1. **Terminal 1 (Backend)**:
   ```bash
   uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
2. **Terminal 2 (Frontend Vite Dev Server)**:
   ```bash
   cd frontend
   npm run dev
   ```
3. Open `http://localhost:3000` (Vite is configured on port 3000 to proxy `/api` and `/ws` to `localhost:8000`).

---

## ☁️ Deployment on Render (Free Plan Recommendations)

The application includes built-in optimizations tailored specifically for resource-constrained hosting (such as Render's 512MB RAM free tier):

- **Calibrated Research Depth**:
  - `Shallow`: 1 Debate Round, 1 Risk Round, up to 2 Tool Calls per Analyst.
  - `Medium`: 1 Debate Round, 2 Risk Rounds, up to 3 Tool Calls per Analyst.
  - `Deep`: 2 Debate Rounds, 2 Risk Rounds, up to 4 Tool Calls per Analyst (context-bounded to prevent OOM).
- **Hard Circuit Breaker**: LangGraph recursion limit set to 100 to prevent runaway graph iterations.
- **WebSocket Keep-Alives**: Heartbeat signals every 5 seconds keep Render's 55-second idle proxy timeout alive.
- **Tool Fallbacks**: If external vendors hit rate limits or blocks, tools gracefully degrade with clean natural language status, allowing the analysis to finalize without crashing.

---

## 📂 Project Directory Structure

```text
Trading-Agents/
├── backend/
│   ├── main.py             # FastAPI web application entry point & static file routing
│   ├── ws_handler.py       # WebSocket streaming handler with keep-alive & thread isolation
│   ├── stats_handler.py    # Real-time token and call tracker callback
│   ├── providers.py        # LLM provider & model registry
│   └── schemas.py          # Pydantic data models for request & state validation
├── frontend/
│   ├── public/
│   │   └── favicon.svg     # Application favicon
│   ├── src/                # React source components (Vite + Finanix styling)
│   ├── dist/               # Compiled production bundle served by FastAPI
│   └── package.json        # Frontend package configuration
├── tradingagents/          # Core multi-agent financial engine
│   ├── agents/             # Agent definitions, system prompts & rating logic
│   ├── dataflows/          # Financial data vendors (Yahoo Finance, Alpha Vantage, SEC EDGAR, etc.)
│   ├── graph/              # LangGraph orchestration, circuit breakers, state propagation
│   ├── llm_clients/        # Unified multi-provider LLM connector factory with exponential backoff
│   └── memory/             # Reflection and memory log storage
├── Dockerfile              # Multi-stage container deployment recipe
├── requirements.txt        # Backend dependencies
└── README.md
```
