"""Server-side configuration driven by environment variables.

Keeps every tunable in one place (see PRODUCT_PLAN.md §12). No provider
API keys live here — BYOK keys arrive per-request only (§12: never put a user
provider key in the server ``.env``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _as_int(raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_host: str
    app_port: int
    app_public_url: str
    app_allowed_hosts: list[str]

    market_provider: str
    market_cache_ttl_seconds: int
    market_timeout_seconds: int

    ai_max_output_tokens: int
    ai_timeout_seconds: int
    ai_first_token_timeout_seconds: int
    ai_max_prompt_chars: int
    ai_allowed_base_urls: list[str]
    # Per-client cap on concurrent AI requests (PRODUCT_PLAN.md §10).
    ai_max_concurrent_per_client: int

    auth_mode: str

    data_dir: str
    deep_max_concurrent_jobs: int
    deep_runner_timeout_seconds: int

    log_level: str

    @property
    def trusted_hosts(self) -> list[str]:
        """Hosts allowed through proxy-auth; an empty list means "all"."""
        return self.app_allowed_hosts


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "production"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=_as_int(os.getenv("APP_PORT"), 8000),
        app_public_url=os.getenv("APP_PUBLIC_URL", "http://localhost:8000"),
        app_allowed_hosts=_split_csv(os.getenv("APP_ALLOWED_HOSTS", "")),
        market_provider=os.getenv("APP_MARKET_PROVIDER", "yfinance"),
        market_cache_ttl_seconds=_as_int(os.getenv("APP_MARKET_CACHE_TTL_SECONDS"), 120),
        market_timeout_seconds=_as_int(os.getenv("APP_MARKET_TIMEOUT_SECONDS"), 15),
        ai_max_output_tokens=_as_int(os.getenv("APP_AI_MAX_OUTPUT_TOKENS"), 2000),
        ai_timeout_seconds=_as_int(os.getenv("APP_AI_TIMEOUT_SECONDS"), 90),
        ai_first_token_timeout_seconds=_as_int(
            os.getenv("APP_AI_FIRST_TOKEN_TIMEOUT_SECONDS"), 30
        ),
        ai_max_prompt_chars=_as_int(os.getenv("APP_AI_MAX_PROMPT_CHARS"), 16000),
        ai_allowed_base_urls=_split_csv(os.getenv("APP_AI_ALLOWED_BASE_URLS", "")),
        ai_max_concurrent_per_client=_as_int(
            os.getenv("APP_AI_MAX_CONCURRENT_PER_CLIENT"), 3
        ),
        auth_mode=os.getenv("APP_AUTH_MODE", "proxy"),
        data_dir=os.getenv("APP_DATA_DIR", "./data"),
        deep_max_concurrent_jobs=_as_int(os.getenv("APP_DEEP_MAX_CONCURRENT_JOBS"), 3),
        deep_runner_timeout_seconds=_as_int(
            os.getenv("APP_DEEP_RUNNER_TIMEOUT_SECONDS"),
            15 * 60,  # deep debate is slow; 15m default
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]