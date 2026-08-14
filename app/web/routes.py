"""HTTP routes (PRODUCT_PLAN.md §6.5).

Routes own validation, HTTP status codes, and rendering only — no analysis or
provider logic here. The analysis stream is SSE; the request body must never be
logged, and any YIELDED error is a user-safe message with the BYOK key already
stripped by construction.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.analysis.models import AnalysisRequest
from app.analysis.module import (
    UnsupportedModeError,
    UnsupportedProviderError,
    stream_analysis,
)
from app.config import get_settings
from app.deep.namespace import resolve_namespace
from app.deep.pool import get_deep_pool
from app.market.models import MarketQuery, Period
from app.market.module import (
    ProviderTimeoutError,
    SymbolNotFoundError,
    get_market_snapshot,
)

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Per-client concurrent-AI-request cap (PRODUCT_PLAN.md §10). Keyed by
# remote address; a plain counter dict guarded by a lock rather than a
# semaphore-per-client because a semaphore only blocks acquire — we want to
# reject over-cap requests immediately (429) rather than queue them behind an
# already-open SSE stream.
_client_active: dict[str, int] = {}
_client_active_lock = asyncio.Lock()


async def _try_acquire_client_slot(client_key: str, limit: int) -> bool:
    async with _client_active_lock:
        current = _client_active.get(client_key, 0)
        if current >= limit:
            return False
        _client_active[client_key] = current + 1
        return True


async def _release_client_slot(client_key: str) -> None:
    async with _client_active_lock:
        current = _client_active.get(client_key, 0)
        if current <= 1:
            _client_active.pop(client_key, None)
        else:
            _client_active[client_key] = current - 1


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(request, "dashboard.html", {
        "default_symbol": "AAPL",
        "periods": [p.value for p in Period],
        "analysis_modes": [
            {"value": "quick", "label": "Quick (single model)"},
            {"value": "deep", "label": "Deep (multi-agent debate)"},
        ],
        "providers": ["openai_compatible", "openai", "anthropic", "gemini"],
        "max_output_tokens": settings.ai_max_output_tokens,
    })


@router.get("/api/market/{symbol}")
async def market_data(symbol: str, period: str = "1Y"):
    try:
        query = MarketQuery(symbol=symbol, period=Period(period))
        snapshot = await get_market_snapshot(query)
        return JSONResponse(content=snapshot.model_dump())
    except SymbolNotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except ProviderTimeoutError as exc:
        return JSONResponse(status_code=504, content={"detail": str(exc)})
    except (ValueError, ValidationError) as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})


@router.post("/api/analysis")
async def analysis(request: Request):
    try:
        body = await request.json()
        analysis_request = AnalysisRequest.model_validate(body)
    except (ValidationError, ValueError, json.JSONDecodeError):
        # Never echo the body back — it may contain the BYOK key.
        return JSONResponse(status_code=422, content={"detail": "invalid request body"})

    namespace = resolve_namespace(request.headers)

    settings = get_settings()
    client_key = request.client.host if request.client else "unknown"
    if not await _try_acquire_client_slot(client_key, settings.ai_max_concurrent_per_client):
        return JSONResponse(
            status_code=429,
            content={"detail": "too many concurrent analysis requests for this client"},
        )

    async def event_stream() -> AsyncIterator[str]:
        try:
            yield _sse("status", f"Starting {analysis_request.analysis_mode.value} analysis…")

            try:
                async for event in stream_analysis(analysis_request, namespace=namespace):
                    yield _sse(event.type, event.message, event.data)
            except (UnsupportedModeError, UnsupportedProviderError) as exc:
                yield _sse("error", str(exc))
            except Exception as exc:  # normalise into a safe, keyless message
                yield _sse("error", exc.__class__.__name__)
        finally:
            await _release_client_slot(client_key)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/config")
async def public_config():
    settings = get_settings()
    return JSONResponse(content={
        "public_url": settings.app_public_url,
        "market_provider": settings.market_provider,
        "ai_max_output_tokens": settings.ai_max_output_tokens,
        "auth_mode": settings.auth_mode,
        "analysis_modes": ["quick", "deep"],
    })


@router.get("/health/live")
async def health_live():
    return JSONResponse(content={"status": "ok"})


@router.get("/health/ready")
async def health_ready():
    settings = get_settings()
    market_ready = settings.market_provider in ("yfinance",)
    try:
        deep_ready = get_deep_pool().ready()
    except Exception:
        deep_ready = False

    ready = market_ready and deep_ready
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "market_data": market_ready,
            "deep_analysis_pool": deep_ready,
        },
    )


def _sse(event_type: str, message: str, data: dict | None = None) -> str:
    payload = json.dumps({"type": event_type, "message": message, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"