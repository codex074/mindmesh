"""Bounded subprocess pool + per-namespace concurrency cap (EXECUTION_PLAN.md C5 / D4).

Concurrency model:

- A global semaphore caps total concurrent deep jobs (``APP_DEEP_MAX_CONCURRENT_JOBS``).
- A per-namespace semaphore (default 1) serialises jobs for the same user, so the
  memory log's atomic tmp+``os.replace()`` writes never race (EXECUTION_PLAN.md D5).
- Different users run in true parallel up to the global cap.
- On cancel/disconnect the caller kills the wrapped subprocess.

This is a local-only scheduler. Swapping it for a real queue (F1) only changes
this module's internals; the adapter interface stays the same.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from app.config import get_settings


class DeepJobPool:
    """Schedules deep-mode runner subprocesses with global + per-user caps."""

    def __init__(
        self,
        max_concurrent_jobs: int | None = None,
        per_namespace: int = 1,
    ) -> None:
        settings = get_settings()
        self._max_concurrent = max_concurrent_jobs or settings.deep_max_concurrent_jobs
        self._per_namespace = per_namespace
        self._global = asyncio.Semaphore(self._max_concurrent)
        self._namespaces: dict[str, asyncio.Semaphore] = {}

    def _namespace_sem(self, namespace: str) -> asyncio.Semaphore:
        sem = self._namespaces.get(namespace)
        if sem is None:
            sem = asyncio.Semaphore(self._per_namespace)
            self._namespaces[namespace] = sem
        return sem

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def active_namespaces(self) -> list[str]:
        return list(self._namespaces)

    def ready(self) -> bool:
        """Health-check hook: the pool is ready if it can be constructed."""
        return self._max_concurrent > 0

    @asynccontextmanager
    async def acquire(self, namespace: str) -> AsyncIterator[None]:
        """Acquire a per-namespace slot, then a global slot (in that order).

        Namespace-first ordering prevents a same-user job from holding a global
        slot while waiting on another user's job that hasn't started yet.
        """
        ns_sem = self._namespace_sem(namespace)
        async with ns_sem:
            async with self._global:
                yield


@lru_cache
def get_deep_pool() -> DeepJobPool:
    """Process-wide singleton pool.

    Must be shared across requests: the global cap and the per-namespace
    lock (D5) only serialise same-user jobs if every request acquires the
    *same* semaphores. Constructing a fresh ``DeepJobPool`` per request (as
    the adapter's default used to do) silently gives each request its own
    uncontended semaphores instead.
    """
    return DeepJobPool()