"""FastAPI application for TradingAgents web frontend."""

import datetime
import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from fastapi.staticfiles import StaticFiles

from backend.schemas import ProviderInfo, ModelOptions, TickerValidation
from backend.providers import get_providers, get_models_for_provider
from backend.ws_handler import websocket_analysis_route

app = FastAPI(
    title="TradingAgents API",
    description="Backend API for the TradingAgents multi-agent LLM trading framework",
    version="0.6.0",
)

# CORS middleware — allow all origins for Vercel / cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ──────────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    """Simple health check for uptime monitoring."""
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}


@app.get("/api/providers", response_model=List[ProviderInfo])
async def list_providers():
    """Return the list of supported LLM providers."""
    return get_providers()


@app.get("/api/models/{provider}")
async def list_models(provider: str):
    """Return available quick and deep models for a provider."""
    return get_models_for_provider(provider)


class TickerRequest(BaseModel):
    ticker: str


CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")


@app.post("/api/validate-ticker", response_model=TickerValidation)
async def validate_ticker(request: TickerRequest):
    """Validate and normalize a ticker symbol."""
    raw = request.ticker.strip()
    if not raw:
        return TickerValidation(valid=False, normalized="", asset_type="unknown",
                                error="Ticker is required")

    # Charset and length check
    if not all(ch.isalnum() or ch in "._-^=" for ch in raw) or len(raw) > 32:
        return TickerValidation(valid=False, normalized=raw.upper(), asset_type="unknown",
                                error="Invalid ticker format")

    # Try to use the project's own normalizer
    try:
        from tradingagents.dataflows.symbols import normalize_symbol
        normalized = normalize_symbol(raw)
    except Exception:
        normalized = raw.upper()

    asset_type = "crypto" if normalized.upper().endswith(CRYPTO_SUFFIXES) else "stock"

    return TickerValidation(valid=True, normalized=normalized, asset_type=asset_type)


@app.get("/api/config/defaults")
async def get_defaults():
    """Return sensible defaults for the setup wizard."""
    return {
        "analysis_date": datetime.date.today().isoformat(),
        "output_language": "English",
        "research_depth": "Shallow",
    }


# ── WebSocket Route ─────────────────────────────────────────────────────────

app.add_api_websocket_route("/ws/analysis", websocket_analysis_route)


# ── Direct run ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Serve React frontend if built; otherwise provide a helpful fallback
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend"
    )
else:
    @app.get("/")
    async def index_fallback():
        return HTMLResponse(
            "<html><body><h2>TradingAgents Backend is running.</h2>"
            "<p>Frontend assets are not yet compiled. Run <code>npm run build</code> in <code>frontend/</code>.</p></body></html>"
        )
