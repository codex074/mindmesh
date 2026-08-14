"""Quick-mode OpenAI-compatible adapter (PRODUCT_PLAN.md §3.3, §6.2).

Streams a single-model analysis from any OpenAI Chat Completions-compatible
endpoint provided by the end user. The BYOK key is used only to build the
outgoing request, never logged or stored. Custom base URLs pass the SSRF guard.
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
from app.security.outbound_url import OutboundUrlValidator, pin_connect_target
from app.security.secrets import ephemeral_secret


class QuickAnalysisError(Exception):
    """Normalised, user-safe quick-mode failure."""


class QuickOpenAICompatibleAdapter:
    """Generic Chat Completions adapter (covers OpenAI and self-hosted endpoints)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._url_validator = OutboundUrlValidator(self._settings.ai_allowed_base_urls)

    async def stream(self, request: AnalysisRequest) -> AsyncIterator[AnalysisEvent]:
        async with ephemeral_secret(request.ai.api_key) as secret:
            async for event in self._stream(request, secret):
                yield event

    async def _stream(self, request: AnalysisRequest, secret) -> AsyncIterator[AnalysisEvent]:
        if not secret:
            raise QuickAnalysisError("an API key is required for quick analysis")
        key = secret.expose()

        model = request.ai.model.strip()
        if not model:
            raise QuickAnalysisError("a model name is required")

        base_url = self._resolve_base_url(request.ai.base_url)
        resolved_ip = self._validate_base_url(base_url)

        # Fetch market snapshot + build deterministic context.
        yield AnalysisEvent(type="status", message="Fetching market data…")
        snapshot = await get_market_snapshot(MarketQuery(symbol=request.symbol))
        context = build_analysis_context(
            snapshot, request.analysis_type, request.user_question,
            max_chars=self._settings.ai_max_prompt_chars,
        )

        url = base_url.rstrip("/") + "/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        request_extensions = {}
        if resolved_ip:
            # Pin the connection to the address we validated, so a DNS record
            # that changes between validation and connection (rebinding)
            # cannot redirect the request to a private/internal address.
            url, original_host = pin_connect_target(url, resolved_ip)
            headers["Host"] = original_host
            request_extensions["sni_hostname"] = original_host
        payload = {
            "model": model,
            "stream": True,
            "max_tokens": self._settings.ai_max_output_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a financial analysis assistant. Separate facts, "
                        "calculations, and assumptions. Never give trade orders or "
                        "guarantee returns. This is educational, not financial advice."
                    ),
                },
                {"role": "user", "content": context.facts},
            ],
        }

        yield AnalysisEvent(type="status", message="Waiting for the model…")

        timeout = httpx.Timeout(
            connect=10.0,
            read=self._settings.ai_timeout_seconds,
            write=30.0,
            pool=10.0,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload, extensions=request_extensions,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise QuickAnalysisError(
                            f"provider returned HTTP {resp.status_code}: "
                            f"{_redact(body.decode(errors='replace'), key)}"
                        )
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
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                        if delta:
                            yield AnalysisEvent(type="token", message=delta)
        except httpx.HTTPError as exc:
            raise QuickAnalysisError(f"provider connection failed: {exc.__class__.__name__}") from exc

        yield AnalysisEvent(type="final", message="")

    def _resolve_base_url(self, base_url: str | None) -> str:
        if base_url:
            return base_url.strip()
        # For the generic provider the plan requires an explicit base URL.
        raise QuickAnalysisError("a base URL is required for the OpenAI-compatible provider")

    def _validate_base_url(self, base_url: str) -> str | None:
        policy = self._url_validator.validate(base_url)
        if not policy.allowed:
            raise QuickAnalysisError(f"base URL rejected: {policy.reason}")
        return policy.resolved_ip


def _redact(text: str, key: str | None = None) -> str:
    """Return a short, secret-scrubbed error snippet for user-facing errors."""
    snippet = text[:200]
    snippet = snippet.replace("Bearer ", "*** ")
    if key:
        snippet = snippet.replace(key, "***")
    return snippet


def create_adapter() -> QuickOpenAICompatibleAdapter:
    return QuickOpenAICompatibleAdapter()