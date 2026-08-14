"""Web route tests (PRODUCT_PLAN.md §6.5, §14).

Uses FastAPI's TestClient against the real app factory with faked market data;
the AI stream is verified against a mocked adapter so no network is touched.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(monkeypatch, snapshot_factory):
    async def fake_snapshot(query):
        return snapshot_factory(query.symbol)

    monkeypatch.setattr("app.web.routes.get_market_snapshot", fake_snapshot)
    return TestClient(create_app())


def test_health_live(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_ready_reports_both_dependencies(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["market_data"] is True
    assert body["deep_analysis_pool"] is True


def test_dashboard_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MindMesh" in resp.text
    assert "Deep (multi-agent debate)" in resp.text


def test_market_data_returns_snapshot(client):
    resp = client.get("/api/market/AAPL?period=1Y")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert len(body["series"]) > 0


def test_market_unknown_symbol_404(monkeypatch, client):
    from app.market.module import SymbolNotFoundError

    async def fake_snapshot(query):
        raise SymbolNotFoundError("no data")

    monkeypatch.setattr("app.web.routes.get_market_snapshot", fake_snapshot)
    resp = client.get("/api/market/NOPE?period=1Y")
    assert resp.status_code == 404


def test_analysis_invalid_body_does_not_echo_secret(client):
    # Invalid JSON body containing a key must never be echoed back.
    resp = client.post("/api/analysis", content='{"ai": {"api_key": "sk-secret"}', headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
    assert "sk-secret" not in resp.text


def test_analysis_unsupported_provider_returns_error_event(client, monkeypatch):
    from app.analysis.module import UnsupportedProviderError
    from app.analysis.models import AnalysisEvent

    async def fake_stream(request, namespace="default"):
        yield AnalysisEvent(type="status", message="start")
        raise UnsupportedProviderError("unknown-provider")

    monkeypatch.setattr("app.web.routes.stream_analysis", fake_stream)

    body = {
        "symbol": "AAPL",
        "analysis_mode": "quick",
        "ai": {"provider": "unknown-provider", "model": "m", "api_key": "sk-secret"},
    }
    resp = client.post("/api/analysis", json=body)
    assert resp.status_code == 200
    assert "sk-secret" not in resp.text
    assert "start" in resp.text


def test_public_config_has_no_secret(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" not in json.dumps(body)
    assert "analysis_modes" in body


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in resp.headers


async def test_per_client_concurrency_cap_rejects_over_limit():
    """PRODUCT_PLAN.md §10: cap concurrent AI requests per client.

    Exercises the actual limiter helpers wired into the /api/analysis route
    (previously the `ai_max_concurrent_per_client` setting was declared but
    never read anywhere).
    """
    from app.web.routes import _try_acquire_client_slot, _release_client_slot

    assert await _try_acquire_client_slot("1.2.3.4", limit=2) is True
    assert await _try_acquire_client_slot("1.2.3.4", limit=2) is True
    # Third concurrent slot for the same client is rejected...
    assert await _try_acquire_client_slot("1.2.3.4", limit=2) is False
    # ...but a different client is unaffected.
    assert await _try_acquire_client_slot("5.6.7.8", limit=2) is True

    await _release_client_slot("1.2.3.4")
    # Freed a slot, so a new request for that client can proceed again.
    assert await _try_acquire_client_slot("1.2.3.4", limit=2) is True