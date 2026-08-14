"""Quick-mode Anthropic adapter (PRODUCT_PLAN.md §3.3 / Phase 3).

Streams a single-model analysis via the Anthropic Messages API.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx

from app.analysis.context import build_analysis_context
from app.analysis.models import AnalysisEvent, AnalysisRequest
from app.config import get_settings
from app.market.models import MarketQuery
from app.market.module import get_market_snapshot
from app.security.secrets import ephemeral_secret

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class QuickAnalysisError(Exception):
    """Normalised, user-safe quick-mode failure."""


class AnthropicAdapter:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def stream(self, request: AnalysisRequest) -> AsyncIterator[AnalysisEvent]:
        async with ephemeral_secret(request.ai.api_key) as secret:
            async for event in self._stream(request, secret):
                yield event

    async def _stream(self, request: AnalysisRequest, secret) -> AsyncIterator[AnalysisEvent]:
        if not secret:
            raise QuickAnalysisError("an API key is required")
        key = secret.expose()
        model = request.ai.model.strip()
        if not model:
            raise QuickAnalysisError("a model name is required")

        yield AnalysisEvent(type="status", message="Fetching market data…")
        snapshot = await get_market_snapshot(MarketQuery(symbol=request.symbol))
        context = build_analysis_context(
            snapshot, request.analysis_type, request.user_question,
            max_chars=self._settings.ai_max_prompt_chars,
        )

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": self._settings.ai_max_output_tokens,
            "stream": True,
            "system": (
                "You are a financial analysis assistant. Separate facts, "
                "calculations, and assumptions. Never give trade orders or "
                "guarantee returns. Educational use, not financial advice."
            ),
            "messages": [{"role": "user", "content": context.facts}],
        }

        yield AnalysisEvent(type="status", message="Waiting for the model…")
        timeout = httpx.Timeout(10.0, read=self._settings.ai_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream("POST", _ANTHROPIC_URL, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise QuickAnalysisError(f"provider returned HTTP {resp.status_code}")
                    lines = resp.aiter_lines()
                    first = True
                    while True:
                        try:
                            if first:
                                line = await asyncio.wait_for(
                                    lines.__anext__(), timeout=self._settings.ai_first_token_timeout_seconds,
                                )
                                first = False
                            else:
                                line = await lines.__anext__()
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError as exc:
                            raise QuickAnalysisError("provider timed out before the first token") from exc
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("type") == "content_block_delta":
                            text = obj.get("delta", {}).get("text", "")
                            if text:
                                yield AnalysisEvent(type="token", message=text)
        except httpx.HTTPError as exc:
            raise QuickAnalysisError(f"provider connection failed: {exc.__class__.__name__}") from exc

        yield AnalysisEvent(type="final", message="")