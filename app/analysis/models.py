"""AI analysis contracts (PRODUCT_PLAN.md §7 + EXECUTION_PLAN.md C2).

``AnalysisRequest`` gains ``analysis_mode: "quick" | "deep"`` (default "quick").
The ``api_key`` must never appear in request dumps, validation errors, or logs.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisType(str, Enum):
    TREND = "trend"
    RISK = "risk"
    VOLATILITY = "volatility"
    TECHNICAL = "technical"


class AnalysisMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"


# Provider identifiers accepted by the quick-mode adapter. ``openai_compatible``
# is the generic endpoint variant (custom base_url).
QUICK_PROVIDERS = ("openai_compatible", "openai", "anthropic", "gemini")


class AIProvider(BaseModel):
    provider: str = "openai_compatible"
    model: str = ""
    api_key: str | None = None
    base_url: str | None = None


class AnalysisRequest(BaseModel):
    symbol: str
    period: str = "1Y"
    analysis_type: AnalysisType = AnalysisType.TREND
    user_question: str | None = None
    analysis_mode: AnalysisMode = AnalysisMode.QUICK
    # Deep-mode only: language for analyst reports and the final decision.
    output_language: str = "English"
    ai: AIProvider

    @field_validator("symbol")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol is required")
        return value

    def redacted(self) -> dict:
        """A safe, loggable view of this request with the key removed."""
        data = self.model_dump()
        ai = data.get("ai") or {}
        if "api_key" in ai:
            ai["api_key"] = "***" if ai["api_key"] else None
        data["ai"] = ai
        return data


class AnalysisEvent(BaseModel):
    """One streamed event to the browser (SSE/NDJSON re-emitted)."""

    type: Literal["status", "token", "section", "final", "error"]
    message: str = ""
    data: dict | None = None