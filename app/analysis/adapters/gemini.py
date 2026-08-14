"""Quick-mode Google Gemini adapter (PRODUCT_PLAN.md §3.3 / Phase 3).

Streams a single-model analysis via the Gemini generateContent stream API.
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

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"


class QuickAnalysisError(Exception):
    """Normalised, user-safe quick-mode failure."""


class GeminiAdapter:
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

        # Send the key as a header, not a `?key=` query param (PRODUCT_PLAN.md
        # §9.2 "no key in URL/query string") — query strings are far more likely
        # to end up in proxy/access logs than headers.
        url = _GEMINI_URL.format(model=model)
        headers = {"x-goog-api-key": key}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": context.facts}],
                }
            ],
            "systemInstruction": {
                "parts": [{
                    "text": (
                        "You are a financial analysis assistant. Separate facts, "
                        "calculations, and assumptions. Never give trade orders or "
                        "guarantee returns. Educational use, not financial advice."
                    )
                }]
            },
            "generationConfig": {"maxOutputTokens": self._settings.ai_max_output_tokens},
        }

        yield AnalysisEvent(type="status", message="Waiting for the model…")
        timeout = httpx.Timeout(10.0, read=self._settings.ai_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
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
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        for candidate in obj.get("candidates", []):
                            for part in candidate.get("content", {}).get("parts", []):
                                text = part.get("text", "")
                                if text:
                                    yield AnalysisEvent(type="token", message=text)
        except httpx.HTTPError as exc:
            raise QuickAnalysisError(f"provider connection failed: {exc.__class__.__name__}") from exc

        yield AnalysisEvent(type="final", message="")