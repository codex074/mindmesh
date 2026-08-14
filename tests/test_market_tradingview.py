"""TradingView technical-intelligence module tests via a fake, no network."""

from __future__ import annotations

import pytest

from app.market.tradingview import (
    TradingViewSymbolNotFoundError,
    TradingViewTimeoutError,
    _fetch_sync,
)


class _FakeAnalysis:
    summary = {"RECOMMENDATION": "BUY", "BUY": 10, "SELL": 2, "NEUTRAL": 3}
    oscillators = {"RECOMMENDATION": "NEUTRAL", "BUY": 3, "SELL": 3, "NEUTRAL": 5, "COMPUTE": {}}
    moving_averages = {"RECOMMENDATION": "BUY", "BUY": 7, "SELL": 0, "NEUTRAL": 5, "COMPUTE": {}}
    indicators = {"RSI": 55.2, "MACD.macd": 1.1, "MACD.signal": 0.9, "SMA20": 190.0,
                  "SMA50": 185.0, "SMA200": 170.0, "EMA20": 191.0, "BB.upper": 200.0,
                  "BB.lower": 180.0, "close": 195.0, "volume": 5000000, "change": 1.2}


class _FakeHandler:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        return _FakeAnalysis()


class _FakeHandlerNone:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        return None  # simulates get_analysis() returning None without raising


class _FakeHandlerNotFound:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        raise Exception("Exchange or symbol not found.")


class _FakeHandlerOtherError:
    def __init__(self, **kwargs):
        pass

    def get_analysis(self):
        raise Exception("Can't access TradingView's API. HTTP status code: 500.")


def test_snapshot_maps_ratings_and_allowlisted_indicators(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandler)
    snapshot = _fetch_sync("AAPL", "NASDAQ", "america", "1d", 10)
    assert snapshot.summary.recommendation == "BUY"
    assert snapshot.oscillators.buy == 3
    assert snapshot.indicators["RSI"] == 55.2
    assert "COMPUTE" not in snapshot.indicators


def test_none_analysis_raises_symbol_not_found(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandlerNone)
    with pytest.raises(TradingViewSymbolNotFoundError):
        _fetch_sync("NOPE", "NASDAQ", "america", "1d", 10)


def test_not_found_message_raises_symbol_not_found(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandlerNotFound)
    with pytest.raises(TradingViewSymbolNotFoundError):
        _fetch_sync("XXXX", "NASDAQ", "america", "1d", 10)


def test_other_error_raises_timeout_error(monkeypatch):
    monkeypatch.setattr("app.market.tradingview.TA_Handler", _FakeHandlerOtherError)
    with pytest.raises(TradingViewTimeoutError):
        _fetch_sync("AAPL", "NASDAQ", "america", "1d", 10)


async def test_cache_returns_same_object(monkeypatch):
    import app.market.tradingview as tv
    from app.market.models import TechnicalRating, TradingViewSnapshot

    snapshot = TradingViewSnapshot(
        symbol="AAPL",
        exchange="NASDAQ",
        screener="america",
        interval="1d",
        as_of="2026-01-01T00:00:00+00:00",
        summary=TechnicalRating(recommendation="BUY", buy=10, sell=2, neutral=3),
        oscillators=TechnicalRating(recommendation="NEUTRAL", buy=3, sell=3, neutral=5),
        moving_averages=TechnicalRating(recommendation="BUY", buy=7, sell=0, neutral=5),
    )

    calls = []

    def fake_fetch(symbol, exchange, screener, interval, timeout):
        calls.append((symbol, exchange, screener, interval))
        return snapshot

    monkeypatch.setattr(tv, "_fetch_sync", fake_fetch)
    monkeypatch.setattr(tv, "_cache", None)

    first = await tv.get_technical_snapshot("AAPL", "NASDAQ", "america", "1d")
    second = await tv.get_technical_snapshot("AAPL", "NASDAQ", "america", "1d")
    assert first is second
    assert len(calls) == 1
