# Trading-Agents 📈

**Trading-Agents** is a modern, full-stack multi-agent LLM financial trading framework. It coordinates teams of specialized AI agents—spanning market data analysis, news evaluation, sentiment tracking, fundamental research, bull/bear investment debates, and risk management—to generate comprehensive, actionable investment reports.

Developed and maintained by **[Vivek Bharadwaj](https://github.com/Vivek1Bharadwaj)**.

---

## 🌟 Highlights & Architecture

- **Multi-Agent Deliberation Pipeline**:
  - **Analyst Team**: Market Analyst, Sentiment Analyst, News Analyst, and Fundamentals Analyst run in parallel.
  - **Research Team**: Bull Researcher and Bear Researcher engage in adversarial debate managed by the Research Manager.
  - **Trading Team**: Formulates trade execution plans based on synthesized research.
  - **Risk Management**: Aggressive, Conservative, and Neutral analysts evaluate portfolio downside and calibrate position limits.
  - **Portfolio Manager**: Final decision arbiter delivering clear signals (`BUY`, `HOLD`, `SELL`, `OVERWEIGHT`, `UNDERWEIGHT`).
- **Web-First Interface**: Real-time interactive UI with WebSocket-streamed logs, per-agent live pipeline state, and live report previews.
- **Finanix Design System**: High-contrast, accessibility-focused (WCAG 2.2 AA compliant) dark theme with custom typography and clean visual metrics.
- **Provider Agnostic**: Out-of-the-box support for OpenAI, Google Gemini, Anthropic Claude, DeepSeek, Groq, Ollama, OpenRouter, and OpenAI-compatible endpoints.

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- **Python**: 3.11 or higher
- **Node.js** (optional, only needed for modifying frontend code)

### 2. Clone the Repository
```bash
git clone https://github.com/Vivek1Bharadwaj/Trading-Agents.git
cd Trading-Agents
```

### 3. Create & Activate a Virtual Environment
```bash
# On Windows:
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a `.env` file in the project root:
```env
# Example configuration:
OPENAI_API_KEY=your_openai_key_here
GOOGLE_API_KEY=your_google_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```
*(You can also input your API keys directly into the web setup wizard at runtime).*

### 6. Run the Application
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🛠️ Frontend Development (Optional)

The pre-built React frontend is already compiled into `frontend/dist/` and served automatically by FastAPI. If you want to customize the React UI:

```bash
cd frontend
npm install
npm run dev
```
The Vite development server will run at `http://localhost:5173`. When finished, compile the production bundle with:
```bash
npm run build
```

---

## 📂 Project Directory Structure

```text
Trading-Agents/
├── backend/
│   ├── main.py             # FastAPI web application entry point & static file routing
│   ├── ws_handler.py       # WebSocket streaming handler for live execution
│   ├── stats_handler.py    # Real-time token and call tracker callback
│   ├── providers.py        # LLM provider & model registry
│   └── schemas.py          # Pydantic data models for request & state validation
├── frontend/
│   ├── src/                # React source components (Vite + Finanix styling)
│   ├── dist/               # Compiled production bundle served by FastAPI
│   └── package.json        # Frontend package configuration
├── tradingagents/          # Core multi-agent financial engine
│   ├── agents/             # Agent definitions, system prompts & rating logic
│   ├── dataflows/          # Financial data vendors (Yahoo Finance, Alpha Vantage, etc.)
│   ├── graph/              # LangGraph orchestration and state propagation
│   ├── llm_clients/        # Unified multi-provider LLM connector factory
│   └── report_html.py      # Standalone HTML report generator
├── Dockerfile              # Container deployment recipe
├── requirements.txt        # Backend dependencies
└── README.md
```

---

## 🛡️ License & Attribution

Designed and created by **[Vivek Bharadwaj](https://github.com/Vivek1Bharadwaj)**. Released under the MIT License.
