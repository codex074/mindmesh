"""AI analysis module + context tests (PRODUCT_PLAN.md §6.2/§6.3)."""

from __future__ import annotations

import pytest

from app.analysis.context import build_analysis_context
from app.analysis.models import AIProvider, AnalysisEvent, AnalysisMode, AnalysisRequest, AnalysisType
from app.analysis.module import stream_analysis


def _make_request(mode=AnalysisMode.QUICK, provider="openai_compatible", key="sk-test"):
    return AnalysisRequest(
        symbol="AAPL",
        period="1Y",
        analysis_type=AnalysisType.TREND,
        analysis_mode=mode,
        ai=AIProvider(provider=provider, model="test-model", api_key=key, base_url="https://api.example.com"),
    )


def test_analysis_request_redacts_api_key():
    req = _make_request()
    dumped = req.redacted()
    assert dumped["ai"]["api_key"] == "***"
    # The model dump (without redaction) would have the key — but redacted() strips it.
    assert "sk-test" not in str(dumped)


def test_analysis_request_normalizes_symbol():
    req = AnalysisRequest(
        symbol="  aapl ",
        analysis_mode=AnalysisMode.QUICK,
        ai=AIProvider(provider="openai_compatible", model="m", api_key="k"),
    )
    assert req.symbol == "AAPL"


def test_build_context_includes_deterministic_facts(snapshot_factory):
    snapshot = snapshot_factory()
    ctx = build_analysis_context(snapshot, AnalysisType.TREND, None)
    assert "AAPL" in ctx.facts
    assert "Latest price" in ctx.facts
    assert "Moving averages" in ctx.facts
    assert ctx.char_count <= 16000


def test_build_context_bounded_to_max_chars(snapshot_factory):
    snapshot = snapshot_factory()
    ctx = build_analysis_context(snapshot, AnalysisType.RISK, "explain", max_chars=200)
    assert ctx.char_count <= 200


async def test_unsupported_quick_provider_raises():
    req = _make_request(provider="unknown-provider")
    with pytest.raises(Exception):
        async for _ in stream_analysis(req):
            pass


async def test_quick_openai_compatible_streams_with_fake_endpoint(monkeypatch, snapshot_factory):
    """Drive the quick adapter against a fake market provider + mocked HTTP."""
    from app.analysis.adapters.openai_compatible import QuickOpenAICompatibleAdapter

    # Fake the market snapshot so no network is touched.
    async def fake_snapshot(query):
        return snapshot_factory(query.symbol)

    monkeypatch.setattr(
        "app.analysis.adapters.openai_compatible.get_market_snapshot",
        fake_snapshot,
    )

    # Replace the URL validator DNS with a pass-through (public host).
    adapter = QuickOpenAICompatibleAdapter()
    adapter._url_validator = _AllowAllValidator()

    class FakeStream:
        def __init__(self):
            self.status_code = 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def aread(self):
            return b""
        def aiter_lines(self):
            async def gen():
                yield 'data: {"choices":[{"delta":{"content":"hello "}}]}'
                yield 'data: {"choices":[{"delta":{"content":"world"}}]}'
                yield "data: [DONE]"
            return gen()

    class FakeClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def stream(self, method, url, headers=None, json=None, extensions=None):
            return FakeStream()

    monkeypatch.setattr("app.analysis.adapters.openai_compatible.httpx.AsyncClient", FakeClient)

    events = []
    async for event in adapter.stream(_make_request()):
        events.append(event)

    tokens = "".join(e.message for e in events if e.type == "token")
    assert tokens == "hello world"
    assert events[-1].type == "final"
    # The key never showed up in any event.
    assert all("sk-test" not in e.message for e in events)


async def test_gemini_sends_key_as_header_not_query_string(monkeypatch, snapshot_factory):
    """PRODUCT_PLAN.md §9.2: the BYOK key must never go in a URL/query
    string (proxy/access logs capture URLs far more readily than headers)."""
    from app.analysis.adapters.gemini import GeminiAdapter

    async def fake_snapshot(query):
        return snapshot_factory(query.symbol)

    monkeypatch.setattr("app.analysis.adapters.gemini.get_market_snapshot", fake_snapshot)

    seen = {}

    class FakeStream:
        status_code = 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def aread(self):
            return b""
        def aiter_lines(self):
            async def gen():
                yield '{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'
            return gen()

    class FakeClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def stream(self, method, url, headers=None, json=None, extensions=None):
            seen["url"] = url
            seen["headers"] = headers or {}
            return FakeStream()

    monkeypatch.setattr("app.analysis.adapters.gemini.httpx.AsyncClient", FakeClient)

    adapter = GeminiAdapter()
    events = [e async for e in adapter.stream(_make_request(provider="gemini", key="sk-gem-secret"))]

    assert "sk-gem-secret" not in seen["url"]
    assert seen["headers"].get("x-goog-api-key") == "sk-gem-secret"
    assert all("sk-gem-secret" not in e.message for e in events)


def test_redact_scrubs_the_actual_key_value_not_just_bearer_prefix():
    from app.analysis.adapters.openai_compatible import _redact

    body = 'you passed key sk-super-secret-123, which is invalid'
    redacted = _redact(body, key="sk-super-secret-123")
    assert "sk-super-secret-123" not in redacted


class _AllowAllValidator:
    def validate(self, url):
        from app.security.outbound_url import UrlPolicy
        return UrlPolicy(url, "api.example.com", True)