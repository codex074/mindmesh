"""Per-user namespace for deep-mode memory logs (EXECUTION_PLAN.md D5 / C4).

The proxy-auth identity (Caddy basic auth, ``APP_AUTH_MODE=proxy``) is resolved
to a stable per-user memory-log path. One shared global log would leak reasoning
across users; a fresh path per job would leave the reflection feature reading an
always-empty log.
"""

from __future__ import annotations

import re
from pathlib import Path

# Headers commonly set by reverse proxies after authenticating a user.
PROXY_IDENTITY_HEADERS = (
    "x-authenticated-user",   # set by Caddy basic_auth + forward_auth passthrough
    "x-webauth-user",         # Caddy ``forward_auth`` convention
    "x-forwarded-user",
)

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")

DEFAULT_NAMESPACE = "default"


def resolve_namespace(headers: dict[str, str] | None) -> str:
    """Resolve the authenticated identity to a safe namespace string."""
    headers = headers or {}
    lowered = {k.lower(): v for k, v in headers.items()}
    for header in PROXY_IDENTITY_HEADERS:
        value = lowered.get(header)
        if value:
            cleaned = _SAFE.sub("_", value.strip()).strip("._") or DEFAULT_NAMESPACE
            return cleaned.lower()
    # No proxy auth header present (local dev / direct access).
    return DEFAULT_NAMESPACE


def memory_log_path_for(namespace: str, data_dir: str) -> Path:
    """Return the per-user memory-log path under ``<data_dir>/memory/``."""
    base = Path(data_dir) / "memory"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{namespace}.md"