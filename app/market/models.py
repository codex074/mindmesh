"""Market data contracts (PRODUCT_PLAN.md §7)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Period(str, Enum):
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"
    FIVE_YEARS = "5Y"
    MAX = "MAX"


# Map period -> (yfinance period, yfinance interval). The interval is chosen to
# keep point counts reasonable and is locked by the plan (§3.1 auto-select).
_PERIOD_TO_PARAMS: dict[Period, tuple[str, str]] = {
    Period.ONE_MONTH: ("1mo", "1d"),
    Period.THREE_MONTHS: ("3mo", "1d"),
    Period.SIX_MONTHS: ("6mo", "1d"),
    Period.ONE_YEAR: ("1y", "1wk"),
    Period.FIVE_YEARS: ("5y", "1mo"),
    Period.MAX: ("max", "1mo"),
}


def period_params(period: Period) -> tuple[str, str]:
    return _PERIOD_TO_PARAMS[period]


class MarketQuery(BaseModel):
    symbol: str
    period: Period = Period.ONE_YEAR
    provider: str = "yfinance"


class SeriesPoint(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketSnapshot(BaseModel):
    symbol: str
    provider: str
    currency: str | None = None
    timezone: str | None = None
    as_of: str
    latest_price: float | None = None
    absolute_change: float | None = None
    percent_change: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    summary_metrics: dict[str, Any] = Field(default_factory=dict)
    series: list[SeriesPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TechnicalRating(BaseModel):
    recommendation: str  # STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL | ERROR
    buy: int
    sell: int
    neutral: int


class TradingViewSnapshot(BaseModel):
    symbol: str
    exchange: str
    screener: str
    interval: str
    as_of: str
    summary: TechnicalRating
    oscillators: TechnicalRating
    moving_averages: TechnicalRating
    indicators: dict[str, float | int | str | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DesktopStudy(BaseModel):
    """One indicator's current values as read off a live TradingView Desktop
    chart — including custom Pine Script indicators, which the public
    TradingView scanner (TradingViewSnapshot above) can never see."""

    name: str
    values: dict[str, str] = Field(default_factory=dict)


class DesktopIndicatorSnapshot(BaseModel):
    requested_symbol: str
    chart_symbol: str
    resolution: str
    as_of: str
    studies: list[DesktopStudy] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
