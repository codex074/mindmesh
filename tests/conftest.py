"""Shared fixtures. Adds the project root to sys.path so `app` imports work
regardless of whether the suite runs from a pip-installed package or directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Test data dir must be writable and isolated per run.
os.environ.setdefault("APP_DATA_DIR", str(ROOT / ".tmp_test_data"))
os.environ.setdefault("APP_DEEP_MAX_CONCURRENT_JOBS", "3")


@pytest.fixture
def snapshot_factory():
    from app.market.models import MarketSnapshot, SeriesPoint

    def _make(symbol="AAPL", n=120):
        series = [
            SeriesPoint(
                timestamp=f"2024-01-{i + 1:02d}",
                open=100.0 + i,
                high=105.0 + i,
                low=98.0 + i,
                close=102.0 + i,
                volume=1_000_000 + i * 10,
            )
            for i in range(n)
        ]
        return MarketSnapshot(
            symbol=symbol,
            provider="yfinance",
            currency="USD",
            timezone="America/New_York",
            as_of="2024-01-30T00:00:00Z",
            latest_price=series[-1].close,
            absolute_change=1.0,
            percent_change=0.5,
            open=series[-1].open,
            high=series[-1].high,
            low=series[-1].low,
            volume=series[-1].volume,
            summary_metrics={
                "period_open": series[0].open,
                "period_high": max(p.high for p in series),
                "period_low": min(p.low for p in series),
                "total_volume": sum(p.volume for p in series),
                "avg_volume": sum(p.volume for p in series) / len(series),
                "volatility_pct": 1.23,
            },
            series=series,
            warnings=[],
        )

    return _make