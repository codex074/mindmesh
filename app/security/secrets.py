"""Request-scoped BYOK secret handling (PRODUCT_PLAN.md §6.4).

A BYOK provider key must live in memory only for the duration of one request,
never be logged, never echo back to the browser, and be released once the
request (or its cancellation) completes. Python cannot guarantee zero copies in
memory, so the contract here is: minimise lifetime and copy count, and make any
accidental ``repr``/traceback redact the value.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator


class RedactedSecret:
    """A str-like holder whose ``repr``/``str`` never leak the raw value.

    Only :meth:`expose` returns the real value; this is the one deliberate
    place the key surfaces.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: str | None) -> None:
        self._raw = raw

    def expose(self) -> str | None:
        return self._raw

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "RedactedSecret(***)"

    def __str__(self) -> str:
        return "***"

    def __bool__(self) -> bool:
        return bool(self._raw)


@asynccontextmanager
async def ephemeral_secret(raw_key: str | None) -> AsyncIterator[RedactedSecret]:
    """Yield a redacted secret holder for the span of one request.

    The holder is deliberately not a bare string, so code that stumbles into
    logging it gets ``***``. The raw key still exists in ``raw_key`` on the
    caller's stack — the caller drops it by going out of scope when the request
    coroutine ends.
    """
    secret = RedactedSecret(raw_key)
    try:
        yield secret
    finally:
        # Drop our reference as soon as the context exits so the key is
        # collectible regardless of what the caller does afterwards.
        secret._raw = None