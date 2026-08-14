"""Market Data module (PRODUCT_PLAN.md §6.1).

Hides the yfinance call, period mapping, timezone normalization, empty/invalid
handling, summary computation, TTL cache, and provider-error translation behind
``get_market_snapshot``. A single fake adapter in tests fulfils the same
signature without touching the network.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from .models import MarketQuery, MarketSnapshot, Period, SeriesPoint, period_params


class MarketDataError(Exception):
    """Normalised, user-safe market-data failure."""


class SymbolNotFoundError(MarketDataError):
    pass


class ProviderTimeoutError(MarketDataError):
    pass


class _TtlCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: dict[tuple[str, str, str], tuple[float, MarketSnapshot]] = {}

    def get(self, key: tuple[str, str, str]) -> MarketSnapshot | None:
        item = self._store.get(key)
        if item is None:
            return None
        inserted, snapshot = item
        if time.monotonic() - inserted > self._ttl:
            self._store.pop(key, None)
            return None
        return snapshot

    def put(self, key: tuple[str, str, str], snapshot: MarketSnapshot) -> None:
        self._store[key] = (time.monotonic(), snapshot)

    def clear(self) -> None:
        self._store.clear()


class MarketDataService:
    """Fetch and normalize OHLCV data for a symbol/period pair."""

    def __init__(self, provider: str = "yfinance", cache_ttl_seconds: int = 120) -> None:
        if provider != "yfinance":
            raise ValueError(f"unsupported market provider: {provider}")
        self.provider = provider
        self._cache = _TtlCache(cache_ttl_seconds)

    async def get_market_snapshot(self, query: MarketQuery) -> MarketSnapshot:
        symbol = query.symbol.strip().upper()
        if not symbol:
            raise SymbolNotFoundError("missing symbol")

        key = (symbol, query.period.value, self.provider)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        snapshot = await self._fetch(symbol, query.period)
        self._cache.put(key, snapshot)
        return snapshot

    async def _fetch(self, symbol: str, period: Period) -> MarketSnapshot:
        symbol = symbol.strip().upper()
        period_arg, interval_arg = period_params(period)
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period_arg, interval=interval_arg, auto_adjust=False)
        except Exception as exc:  # yfinance raises a mix of network/parse errors
            raise ProviderTimeoutError(f"provider error for {symbol}") from exc

        if df is None or df.empty:
            raise SymbolNotFoundError(f"no data found for symbol {symbol}")

        # Yfinance returns rows in ascending date order with a tz-aware DatetimeIndex.
        df = df.dropna(subset=["Close"])
        if df.empty:
            raise SymbolNotFoundError(f"no clean price data for symbol {symbol}")

        tz = df.index.tz
        tz_name = _timezone_name(tz)

        currency = None
        try:
            info = ticker.get_info() or {}
            currency = info.get("currency") or info.get("financialCurrency")
        except Exception:
            currency = None

        series = [
            SeriesPoint(
                timestamp=idx.strftime("%Y-%m-%d"),
                open=_nan0(float(row.Open)),
                high=_nan0(float(row.High)),
                low=_nan0(float(row.Low)),
                close=_nan0(float(row.Close)),
                volume=_nan0(float(row.Volume)),
            )
            for idx, row in df.iterrows()
        ]

        latest_row = df.iloc[-1]
        latest = float(latest_row.Close)
        previous = _previous_close(df)
        abs_change = None if previous is None else round(latest - previous, 4)
        pct_change = None if previous in (None, 0) else round((latest - previous) / previous * 100, 4)

        period_high = float(df.High.max())
        period_low = float(df.Low.min())
        period_open = float(df.iloc[0].Open)
        total_volume = float(df.Volume.sum())

        summary_metrics = {
            "period_open": round(period_open, 4),
            "period_high": round(period_high, 4),
            "period_low": round(period_low, 4),
            "total_volume": round(total_volume, 2),
            "avg_volume": round(float(df.Volume.mean()), 2),
            "volatility_pct": round(float(df.Close.pct_change().std() * 100), 4),
            "points": len(series),
        }

        return MarketSnapshot(
            symbol=symbol,
            provider=self.provider,
            currency=currency,
            timezone=tz_name,
            as_of=datetime.now(timezone.utc).isoformat(),
            latest_price=round(latest, 4),
            absolute_change=abs_change,
            percent_change=pct_change,
            open=round(float(latest_row.Open), 4),
            high=round(period_high, 4),
            low=round(period_low, 4),
            volume=round(float(latest_row.Volume), 2),
            summary_metrics=summary_metrics,
            series=series,
            warnings=[],
        )


def _previous_close(df: Any) -> float | None:
    """The close preceding the latest point, used for daily change."""
    if len(df) < 2:
        return None
    return float(df.Close.iloc[-2])


def _timezone_name(tz) -> str:
    """Return a human-readable timezone name across pytz and zoneinfo objects."""
    if tz is None:
        return "UTC"
    # zoneinfo.ZoneInfo exposes `.key`; pytz exposes `.zone`.
    return getattr(tz, "key", None) or getattr(tz, "zone", None) or str(tz)


def _nan0(value: float) -> float:
    return 0.0 if value != value else value  # NaN check


_default_service: MarketDataService | None = None


async def get_market_snapshot(query: MarketQuery) -> MarketSnapshot:
    """Module-level entrypoint; lazily builds the default service."""
    global _default_service
    if _default_service is None:
        from app.config import get_settings

        settings = get_settings()
        _default_service = MarketDataService(
            provider=settings.market_provider,
            cache_ttl_seconds=settings.market_cache_ttl_seconds,
        )
    return await _default_service.get_market_snapshot(query)