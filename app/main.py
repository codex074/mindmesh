"""FastAPI app factory (PRODUCT_PLAN.md §5, §11, §12).

Single app object with the web routes mounted. Secure headers are applied
globally via middleware. The app is created by ``create_app`` so tests can
build it against fake adapters without touching the network.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.web.routes import router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # No-op unless the TradingView Desktop bridge was ever used — otherwise
    # its spawned Node/CDP subprocess would outlive this process.
    from app.market.tradingview_desktop import close_bridge

    await close_bridge()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MindMesh",
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.middleware("http")
    async def secure_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # CSP is kept permissive for the SSE + inline-script dashboard; tighten once
        # the production template is finalised.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
        )
        if settings.app_env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()