"""Analysis Context module (PRODUCT_PLAN.md §6.3).

Builds a bounded, deterministic context string from a ``MarketSnapshot`` for
injection into an AI prompt. It sends only the necessary facts (returns,
volatility, moving averages, drawdown, volume summary) — never the raw
dataframe — and separates computed facts from AI opinion by construction: the
model is told these are deterministic calculations.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.market.models import MarketSnapshot

from .models import AnalysisType


@dataclass(frozen=True)
class AnalysisContext:
    symbol: str
    analysis_type: AnalysisType
    facts: str
    char_count: int


_ANALYSIS_TYPE_INSTRUCTIONS = {
    AnalysisType.TREND: "Summarise the price trend from the provided series.",
    AnalysisType.RISK: "Assess the risk profile (volatility, drawdown, volume).",
    AnalysisType.VOLATILITY: "Explain the observed volatility and volume behaviour.",
    AnalysisType.TECHNICAL: "Give a technical summary from the data; no trade advice.",
}


def build_analysis_context(
    snapshot: MarketSnapshot,
    analysis_type: AnalysisType,
    user_question: str | None,
    max_chars: int = 16000,
) -> AnalysisContext:
    closes = [p.close for p in snapshot.series if p.close > 0]
    returns = [_pct_change(a, b) for a, b in zip(closes, closes[1:])] if len(closes) > 1 else []

    facts_lines = [
        f"Symbol: {snapshot.symbol}",
        f"Provider: {snapshot.provider}",
        f"Data timezone: {snapshot.timezone or 'unknown'}",
        f"As of: {snapshot.as_of}",
        f"Latest price: {snapshot.latest_price}",
        f"Absolute change: {snapshot.absolute_change}",
        f"Percent change: {snapshot.percent_change}%",
        f"Open/High/Low: {snapshot.open} / {snapshot.high} / {snapshot.low}",
        f"Latest volume: {snapshot.volume}",
    ]

    if snapshot.summary_metrics:
        m = snapshot.summary_metrics
        facts_lines.append(
            f"Summary metrics: period_open={m.get('period_open')}, period_high={m.get('period_high')}, "
            f"period_low={m.get('period_low')}, total_volume={m.get('total_volume')}, "
            f"volatility_pct(1-sigma)={m.get('volatility_pct')}"
        )

    if returns:
        avg = sum(returns) / len(returns)
        variance = sum((r - avg) ** 2 for r in returns) / len(returns)
        stddev = variance ** 0.5
        facts_lines.append(f"Return stats: mean={avg:.4f}%, std={stddev:.4f}% (over {len(returns)} intervals)")

    ma_short = _moving_average(closes, min(20, len(closes)))
    ma_long = _moving_average(closes, min(50, len(closes)))
    if ma_short is not None and ma_long is not None:
        facts_lines.append(f"Moving averages: short={ma_short:.4f}, long={ma_long:.4f}")

    drawdown = _max_drawdown_pct(closes)
    if drawdown is not None:
        facts_lines.append(f"Max drawdown over period: {drawdown:.3f}%")

    # Summary of the series tail only — the model gets the shape, not the spreadsheet.
    facts_lines.append(f"Series points: {len(snapshot.series)}")
    tail = _series_tail(snapshot, n=5)
    if tail:
        facts_lines.append("Last prices (date: close):")
        facts_lines.extend(f"  {ts}: {close}" for ts, close in tail)

    facts = "\n".join(facts_lines)
    instruction = _ANALYSIS_TYPE_INSTRUCTIONS[analysis_type]
    if user_question:
        instruction += f"\nUser question: {user_question}"

    full = f"{instruction}\n\nDeterministic data (computed, not opinion):\n{facts}"
    if len(full) > max_chars:
        full = full[: max_chars - 1] + "…"

    return AnalysisContext(symbol=snapshot.symbol, analysis_type=analysis_type, facts=full, char_count=len(full))


def _pct_change(prev: float, cur: float) -> float:
    if prev in (0, None):
        return 0.0
    return (cur - prev) / prev * 100


def _moving_average(values: list[float], window: int) -> float | None:
    if not values:
        return None
    window = max(1, min(window, len(values)))
    return sum(values[-window:]) / window


def _max_drawdown_pct(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    max_dd = 0.0
    for c in closes[1:]:
        if c > peak:
            peak = c
        dd = (peak - c) / peak * 100 if peak else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _series_tail(snapshot: MarketSnapshot, n: int = 5) -> list[tuple[str, float]]:
    return [(p.timestamp, p.close) for p in snapshot.series[-n:]]