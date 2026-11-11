"""Unit and integration tests for backend REST endpoints and WebSocket analysis handler."""

import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.ws_handler import _build_complete_report


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_list_providers(client):
    response = client.get("/api/providers")
    assert response.status_code == 200
    providers = response.json()
    assert isinstance(providers, list)
    assert len(providers) > 0
    keys = [p["key"] for p in providers]
    assert "openai" in keys


def test_list_models(client):
    response = client.get("/api/models/openai")
    assert response.status_code == 200
    data = response.json()
    assert "quick" in data
    assert "deep" in data
    assert len(data["quick"]) > 0


def test_validate_ticker(client):
    # Valid stock ticker
    res = client.post("/api/validate-ticker", json={"ticker": "aapl"})
    assert res.status_code == 200
    assert res.json()["valid"] is True
    assert res.json()["normalized"] == "AAPL"
    assert res.json()["asset_type"] == "stock"

    # Valid crypto ticker
    res = client.post("/api/validate-ticker", json={"ticker": "btc-usd"})
    assert res.status_code == 200
    assert res.json()["valid"] is True
    assert res.json()["asset_type"] == "crypto"

    # Empty ticker
    res = client.post("/api/validate-ticker", json={"ticker": "   "})
    assert res.status_code == 200
    assert res.json()["valid"] is False

    # Invalid characters
    res = client.post("/api/validate-ticker", json={"ticker": "INVALID!@#$%"})
    assert res.status_code == 200
    assert res.json()["valid"] is False


def test_config_defaults(client):
    response = client.get("/api/config/defaults")
    assert response.status_code == 200
    data = response.json()
    assert "analysis_date" in data
    assert data["output_language"] == "English"


def test_build_complete_report():
    final_state = {
        "market_report": "Market outlook is bullish.",
        "sentiment_report": "Social sentiment is overwhelmingly positive.",
        "news_report": "Positive quarterly earnings report.",
        "fundamentals_report": "Strong balance sheet with zero debt.",
        "investment_plan": "Accumulate on pullbacks.",
        "trader_investment_plan": "Place limit buy order at support.",
        "final_trade_decision": "BUY with target 150.",
    }
    sections = {}
    report = _build_complete_report(final_state, sections)
    assert "## Market Analysis" in report
    assert "Market outlook is bullish." in report
    assert "## Sentiment Analysis" in report
    assert "## News Analysis" in report
    assert "## Fundamentals Analysis" in report
    assert "## Investment Plan" in report
    assert "## Trading Plan" in report
    assert "## Final Decision" in report
    assert "BUY with target 150." in report


def test_websocket_invalid_config(client):
    with client.websocket_connect("/ws/analysis") as websocket:
        websocket.send_text("not-a-json")
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Invalid configuration" in data["data"]["message"]


def test_websocket_analysis_flow(client):
    mock_graph = mock.MagicMock()
    mock_graph.create_run_state.return_value = {"company_of_interest": "AAPL", "trade_date": "2025-01-01"}
    mock_graph.propagator.get_graph_args.return_value = {"stream_mode": "values", "config": {"recursion_limit": 100}}
    mock_graph.propagator.max_recur_limit = 100
    mock_graph.save_reports.return_value = "/fake/report/complete_report.md"

    def dummy_stream(*args, **kwargs):
        yield ((), "values", {
            "company_of_interest": "AAPL",
            "trade_date": "2025-01-01",
            "final_trade_decision": "BUY AAPL",
        })

    mock_graph.graph.stream = dummy_stream

    with mock.patch("tradingagents.graph.trading_graph.TradingAgentsGraph", return_value=mock_graph):
        with client.websocket_connect("/ws/analysis") as ws:
            ws.send_json({
                "ticker": "AAPL",
                "analysis_date": "2025-01-01",
                "output_language": "English",
                "analysts": ["market"],
                "research_depth": "shallow",
                "llm_provider": "openai",
                "quick_think_llm": "gpt-4o-mini",
                "deep_think_llm": "gpt-4o",
                "api_key": "fake_key",
            })
            types = []
            complete_data = None
            while True:
                msg = ws.receive_json()
                types.append(msg["type"])
                if msg["type"] == "complete":
                    complete_data = msg["data"]
                    break
                elif msg["type"] == "error":
                    pytest.fail(f"Unexpected error: {msg}")

            assert "complete" in types
            assert complete_data is not None
            assert complete_data["report_path"] == "/fake/report/complete_report.md"
            assert mock_graph.save_reports.called
