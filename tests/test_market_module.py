"""Market Data module tests via a fake, no network (PRODUCT_PLAN.md §14)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.market.models import MarketQuery, Period
from app.market.module import MarketDataService, SymbolNotFoundError


class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, period, interval, auto_adjust):
        return self._df

    def get_info(self):
        return {"currency": "USD"}


def _make_df():
    idx = pd.date_range("2024-01-01", periods=5, freq="B", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104],
            "High": [105, 106, 107, 108, 109],
            "Low": [99, 100, 101, 102, 103],
            "Close": [104, 105, 106, 107, 108],
            "Volume": [1000, 1100, 1200, 1300, 1400],
        },
        index=idx,
    )


async def test_snapshot_normalizes_symbol_and_series(monkeypatch):
    monkeypatch.setattr(
        "app.market.module.yf.Ticker", lambda sym: _FakeTicker(_make_df())
    )
    service = MarketDataService(provider="yfinance", cache_ttl_seconds=120)

    snapshot = await service._fetch("aapl", Period.ONE_MONTH)

    assert snapshot.symbol == "AAPL"
    assert snapshot.currency == "USD"
    assert snapshot.timezone == "America/New_York"
    assert snapshot.latest_price == 108.0
    assert snapshot.absolute_change == 1.0
    assert len(snapshot.series) == 5
    assert snapshot.series[0].close == 104.0


async def test_empty_data_raises_symbol_not_found(monkeypatch):
    monkeypatch.setattr(
        "app.market.module.yf.Ticker", lambda sym: _FakeTicker(pd.DataFrame())
    )
    service = MarketDataService()
    with pytest.raises(SymbolNotFoundError):
        await service._fetch("NOPE", Period.ONE_MONTH)


def test_invalid_provider_rejected():
    with pytest.raises(ValueError):
        MarketDataService(provider="not-a-provider")


def test_cache_returns_same_object():
    service = MarketDataService(cache_ttl_seconds=60)
    key = ("AAPL", "1Y", "yfinance")
    from app.market.models import MarketSnapshot

    snap = MarketSnapshot(symbol="AAPL", provider="yfinance", as_of="x", series=[])
    service._cache.put(key, snap)
    assert service._cache.get(key) is snap