"""TradingView Desktop bridge tests via a fake session, no real subprocess/CDP."""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from app.market import tradingview_desktop as tvd
from app.market.tradingview_desktop import (
    TradingViewDesktopBridgeError,
    TradingViewDesktopTimeoutError,
    TradingViewDesktopUnavailableError,
    get_desktop_indicator_snapshot,
)


def test_disabled_by_default_raises_unavailable():
    """Default settings have the bridge off — this must not silently try to
    spawn a subprocess or hang; it should fail fast and clearly."""
    with pytest.raises(TradingViewDesktopUnavailableError):
        tvd._get_bridge()


class _FakeBridge:
    """Mirrors the real _DesktopBridge's public surface: a lock the caller
    holds for the whole multi-step operation, call_tool(), and close()."""

    def __init__(self, responses: dict[str, list[dict]]):
        self._responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, dict]] = []
        self.lock = asyncio.Lock()
        self.close_calls = 0

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        queue = self._responses.get(name)
        if not queue:
            raise TradingViewDesktopBridgeError(f"no fake response queued for {name}")
        return queue.pop(0)

    async def close(self) -> None:
        self.close_calls += 1


async def test_snapshot_without_symbol_reads_state_and_values(monkeypatch):
    fake = _FakeBridge({
        "chart_get_state": [{"success": True, "symbol": "OANDA:XAUUSD", "resolution": "5"}],
        "data_get_study_values": [{
            "success": True,
            "studies": [{"name": "EMA 13/34/89/200", "values": {"Plot": "4,366.44"}}],
        }],
    })
    monkeypatch.setattr(tvd, "_get_bridge", lambda: fake)

    snapshot = await get_desktop_indicator_snapshot()

    assert snapshot.chart_symbol == "OANDA:XAUUSD"
    assert snapshot.studies[0].name == "EMA 13/34/89/200"
    assert snapshot.studies[0].values["Plot"] == "4,366.44"
    assert [c[0] for c in fake.calls] == ["chart_get_state", "data_get_study_values"]


async def test_snapshot_with_symbol_switches_chart_first(monkeypatch):
    fake = _FakeBridge({
        "chart_set_symbol": [{"success": True, "symbol": "AAPL"}],
        "chart_get_state": [{"success": True, "symbol": "BATS:AAPL", "resolution": "5"}],
        "data_get_study_values": [{"success": True, "studies": []}],
    })
    monkeypatch.setattr(tvd, "_get_bridge", lambda: fake)
    monkeypatch.setattr(tvd, "_SYMBOL_SWITCH_SETTLE_SECONDS", 0)

    snapshot = await get_desktop_indicator_snapshot("AAPL")

    assert snapshot.requested_symbol == "AAPL"
    assert snapshot.chart_symbol == "BATS:AAPL"  # exchange-prefixed; base-symbol match still confirms
    assert snapshot.warnings == []
    assert fake.calls[0] == ("chart_set_symbol", {"symbol": "AAPL"})


async def test_symbol_match_is_exact_not_substring(monkeypatch):
    """A chart symbol that merely *contains* the requested ticker as a
    substring (e.g. stale state showing an unrelated symbol) must not be
    treated as a confirmed switch."""
    fake = _FakeBridge({
        "chart_set_symbol": [{"success": True, "symbol": "MU"}],
        "chart_get_state": [{"success": True, "symbol": "NASDAQ:AMUZN", "resolution": "5"}]
        * (tvd._SYMBOL_SWITCH_POLL_ATTEMPTS + 1),
        "data_get_study_values": [{"success": True, "studies": []}],
    })
    monkeypatch.setattr(tvd, "_get_bridge", lambda: fake)
    monkeypatch.setattr(tvd, "_SYMBOL_SWITCH_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(tvd, "_SYMBOL_SWITCH_SETTLE_SECONDS", 0)

    snapshot = await get_desktop_indicator_snapshot("MU")

    assert snapshot.warnings != []


async def test_concurrent_requests_do_not_interleave_chart_switches(monkeypatch):
    """The whole switch+read sequence must run under one lock acquisition —
    otherwise a second request's chart_set_symbol can land between the
    first request's switch and its read, returning the wrong symbol's data."""
    fake = _FakeBridge({
        "chart_set_symbol": [{"success": True, "symbol": "AAPL"}, {"success": True, "symbol": "TSLA"}],
        "chart_get_state": [
            {"success": True, "symbol": "AAPL", "resolution": "5"},
            {"success": True, "symbol": "TSLA", "resolution": "5"},
        ],
        "data_get_study_values": [
            {"success": True, "studies": [{"name": "S", "values": {"Plot": "AAPL-value"}}]},
            {"success": True, "studies": [{"name": "S", "values": {"Plot": "TSLA-value"}}]},
        ],
    })
    monkeypatch.setattr(tvd, "_get_bridge", lambda: fake)
    monkeypatch.setattr(tvd, "_SYMBOL_SWITCH_SETTLE_SECONDS", 0)

    results = await asyncio.gather(
        get_desktop_indicator_snapshot("AAPL"),
        get_desktop_indicator_snapshot("TSLA"),
    )

    values_by_symbol = {r.requested_symbol: r.studies[0].values["Plot"] for r in results}
    assert values_by_symbol["AAPL"] == "AAPL-value"
    assert values_by_symbol["TSLA"] == "TSLA-value"
    # Calls must not interleave: each chart_set_symbol is immediately
    # followed by that same request's chart_get_state/data_get_study_values,
    # never by the other request's chart_set_symbol.
    names = [c[0] for c in fake.calls]
    assert names == [
        "chart_set_symbol", "chart_get_state", "data_get_study_values",
        "chart_set_symbol", "chart_get_state", "data_get_study_values",
    ]


async def test_bridge_tool_error_propagates(monkeypatch):
    fake = _FakeBridge({})  # no responses queued -> immediate bridge error
    monkeypatch.setattr(tvd, "_get_bridge", lambda: fake)

    with pytest.raises(TradingViewDesktopBridgeError):
        await get_desktop_indicator_snapshot()


async def test_close_bridge_stops_the_fake_bridge_and_clears_singleton(monkeypatch):
    fake = _FakeBridge({})
    monkeypatch.setattr(tvd, "_bridge", fake)

    await tvd.close_bridge()

    assert fake.close_calls == 1
    assert tvd._bridge is None


async def test_real_bridge_worker_starts_and_closes_cleanly(monkeypatch):
    """Exercises the actual _DesktopBridge worker-task lifecycle (not the
    fake) against a stubbed mcp session, to catch task-affinity / cleanup
    bugs in the real class that a pure-fake test can't see. Regression test
    for: entering the mcp session's cancel scopes in one task (a caller
    wrapped in asyncio.wait_for) and exiting them in another (close_bridge)
    raises "Attempted to exit cancel scope in a different task than it was
    entered in" and leaks the subprocess."""

    class _FakeContent:
        type = "text"
        text = json.dumps({"success": True, "echo": "ok"})

    class _FakeResult:
        content = [_FakeContent()]
        isError = False

    class _FakeSession:
        def __init__(self, read, write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def initialize(self):
            pass

        async def call_tool(self, name, arguments):
            return _FakeResult()

    class _FakeStdioClient:
        def __init__(self, params):
            pass

        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, *exc_info):
            return False

    def _fake_stdio_client(params):
        return _FakeStdioClient(params)

    fake_mcp = types.SimpleNamespace(ClientSession=_FakeSession, StdioServerParameters=lambda **kw: kw)
    fake_mcp_stdio = types.SimpleNamespace(stdio_client=_fake_stdio_client)
    fake_mcp_client = types.SimpleNamespace(stdio=fake_mcp_stdio)
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_mcp_client)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", fake_mcp_stdio)

    bridge = tvd._DesktopBridge(command="node", args=["fake.js"], timeout=5)

    result = await bridge.call_tool("some_tool", {})
    assert result == {"success": True, "echo": "ok"}
    assert bridge._worker is not None and not bridge._worker.done()

    await bridge.close()

    assert bridge._worker.done()


async def test_overall_timeout_wraps_the_whole_operation(monkeypatch):
    class _HangingBridge(_FakeBridge):
        async def call_tool(self, name, arguments):
            await asyncio.sleep(5)

    fake = _HangingBridge({})
    monkeypatch.setattr(tvd, "_get_bridge", lambda: fake)

    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("APP_MARKET_TV_DESKTOP_TIMEOUT_SECONDS", "1")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(TradingViewDesktopTimeoutError):
            await get_desktop_indicator_snapshot("AAPL")
    finally:
        config.get_settings.cache_clear()
