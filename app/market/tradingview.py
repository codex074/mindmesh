"""TradingView Technical Intelligence module (additive to app/market/module.py).

Wraps tradingview-ta's TA_Handler to surface TradingView's own rule-based
technical rating (RSI/MACD/moving-averages/overall BUY-SELL-NEUTRAL
consensus) for a single symbol. Not a replacement for the yfinance
market-data path in app/market/module.py: TradingView's public libraries do
not return a historical OHLCV series for one symbol, only point-in-time
indicator snapshots. No API key required.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from tradingview_ta import TA_Handler

from .models import TechnicalRating, TradingViewSnapshot


class TradingViewError(Exception):
    """Normalised, user-safe TradingView failure."""


class TradingViewSymbolNotFoundError(TradingViewError):
    pass


class TradingViewTimeoutError(TradingViewError):
    pass


# Allowlist of raw tradingview_ta indicator keys, expanded to TradingView's
# full default value set. Deliberately excludes "Recommend.*"/"Rec.*" keys —
# those are pure BUY/SELL/NEUTRAL classification labels already surfaced via
# summary/oscillators/moving_averages, not indicator readings.
_INDICATOR_ALLOWLIST = (
    "close", "open", "high", "low", "volume", "change",
    "RSI", "RSI[1]",
    "Stoch.K", "Stoch.D", "Stoch.K[1]", "Stoch.D[1]", "Stoch.RSI.K",
    "CCI20", "CCI20[1]",
    "ADX", "ADX+DI", "ADX-DI", "ADX+DI[1]", "ADX-DI[1]",
    "AO", "AO[1]", "AO[2]",
    "Mom", "Mom[1]",
    "MACD.macd", "MACD.signal",
    "W.R", "BBPower", "UO",
    "EMA5", "SMA5", "EMA10", "SMA10", "EMA20", "SMA20", "EMA30", "SMA30",
    "EMA50", "SMA50", "EMA100", "SMA100", "EMA200", "SMA200",
    "Ichimoku.BLine", "VWMA", "HullMA9", "P.SAR",
    "BB.upper", "BB.lower",
    "Pivot.M.Classic.S3", "Pivot.M.Classic.S2", "Pivot.M.Classic.S1",
    "Pivot.M.Classic.Middle", "Pivot.M.Classic.R1", "Pivot.M.Classic.R2", "Pivot.M.Classic.R3",
    "Pivot.M.Fibonacci.S3", "Pivot.M.Fibonacci.S2", "Pivot.M.Fibonacci.S1",
    "Pivot.M.Fibonacci.Middle", "Pivot.M.Fibonacci.R1", "Pivot.M.Fibonacci.R2", "Pivot.M.Fibonacci.R3",
    "Pivot.M.Camarilla.S3", "Pivot.M.Camarilla.S2", "Pivot.M.Camarilla.S1",
    "Pivot.M.Camarilla.Middle", "Pivot.M.Camarilla.R1", "Pivot.M.Camarilla.R2", "Pivot.M.Camarilla.R3",
    "Pivot.M.Woodie.S3", "Pivot.M.Woodie.S2", "Pivot.M.Woodie.S1",
    "Pivot.M.Woodie.Middle", "Pivot.M.Woodie.R1", "Pivot.M.Woodie.R2", "Pivot.M.Woodie.R3",
    "Pivot.M.Demark.S1", "Pivot.M.Demark.Middle", "Pivot.M.Demark.R1",
)


class _TtlCache:
    """Keyed by (symbol, exchange, screener, interval). Not shared with
    app/market/module.py's cache — that one is typed for MarketSnapshot."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: dict[tuple[str, str, str, str], tuple[float, TradingViewSnapshot]] = {}

    def get(self, key):
        item = self._store.get(key)
        if item is None:
            return None
        inserted, snapshot = item
        if time.monotonic() - inserted > self._ttl:
            self._store.pop(key, None)
            return None
        return snapshot

    def put(self, key, snapshot) -> None:
        self._store[key] = (time.monotonic(), snapshot)


def _rating(block: dict) -> TechnicalRating:
    return TechnicalRating(
        recommendation=block.get("RECOMMENDATION", "ERROR"),
        buy=block.get("BUY", 0),
        sell=block.get("SELL", 0),
        neutral=block.get("NEUTRAL", 0),
    )


def _fetch_sync(symbol: str, exchange: str, screener: str, interval: str, timeout: int) -> TradingViewSnapshot:
    """Blocking — always invoke via asyncio.to_thread, never inline in an
    async def. TA_Handler.get_analysis() uses synchronous `requests`; calling
    it directly in an async handler would block the whole event loop,
    including any in-flight SSE analysis streams."""
    handler = TA_Handler(
        symbol=symbol,
        exchange=exchange,
        screener=screener,
        interval=interval,
        timeout=timeout,  # TA_Handler defaults to timeout=None (hangs forever) — always pass explicitly
    )
    try:
        analysis = handler.get_analysis()
    except Exception as exc:  # tradingview_ta raises bare Exception for all failures
        message = str(exc)
        if "not found" in message.lower():
            raise TradingViewSymbolNotFoundError(
                f"no TradingView analysis for {exchange}:{symbol} ({screener})"
            ) from exc
        raise TradingViewTimeoutError(f"TradingView provider error for {symbol}") from exc

    # get_analysis() can return None (not raise) when TradingView's core
    # Recommend.Other/Recommend.All columns come back null for this pair.
    # Verified directly against tradingview_ta 3.3.0 source (main.py calculate()).
    if analysis is None:
        raise TradingViewSymbolNotFoundError(
            f"no TradingView analysis for {exchange}:{symbol} ({screener})"
        )

    indicators = {k: analysis.indicators.get(k) for k in _INDICATOR_ALLOWLIST}

    return TradingViewSnapshot(
        symbol=symbol,
        exchange=exchange,
        screener=screener,
        interval=interval,
        as_of=datetime.now(timezone.utc).isoformat(),  # analysis.time is naive local time; don't use it
        summary=_rating(analysis.summary),
        oscillators=_rating(analysis.oscillators),
        moving_averages=_rating(analysis.moving_averages),
        indicators=indicators,
        warnings=[],
    )


_cache: _TtlCache | None = None


async def get_technical_snapshot(
    symbol: str,
    exchange: str,
    screener: str,
    interval: str = "1d",
) -> TradingViewSnapshot:
    """Module-level entrypoint; mirrors get_market_snapshot's lazy-default
    shape but stays fully independent of it."""
    global _cache
    from app.config import get_settings

    settings = get_settings()
    if _cache is None:
        _cache = _TtlCache(settings.market_tv_cache_ttl_seconds)

    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    screener = screener.strip().lower()
    key = (symbol, exchange, screener, interval)

    cached = _cache.get(key)
    if cached is not None:
        return cached

    snapshot = await asyncio.to_thread(
        _fetch_sync, symbol, exchange, screener, interval, settings.market_tv_timeout_seconds
    )
    _cache.put(key, snapshot)
    return snapshot