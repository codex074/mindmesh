"""AI provider adapters behind the ``stream_analysis`` seam."""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from app.analysis.models import AnalysisEvent, AnalysisRequest


class AnalysisAdapter(Protocol):
    """Contract every adapter (quick or deep) implements."""

    async def stream(self, request: AnalysisRequest) -> AsyncIterator[AnalysisEvent]:
        ...