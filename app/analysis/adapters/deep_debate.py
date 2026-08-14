"""Deep-mode adapter (EXECUTION_PLAN.md C6): run TradingAgents in a subprocess.

Mirrors the quick adapter's ``stream()`` shape but sources events from the
``app.deep.runner`` subprocess, which runs one TradingAgents debate per process
(sidestepping the framework's module-global config). The provider key is passed
only via the subprocess's minimal env, never argv/stdin/logs.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import AsyncIterator

from app.analysis.models import AnalysisEvent, AnalysisRequest
from app.config import get_settings
from app.deep.namespace import DEFAULT_NAMESPACE, memory_log_path_for
from app.deep.pool import DeepJobPool, get_deep_pool
from app.security.secrets import ephemeral_secret

# mindmesh provider -> TradingAgents provider, plus the provider's API-key env var.
# Mirrors tradingagents/llm_clients/api_key_env.py without importing it here, so
# quick mode never pulls the TradingAgents dependency.
_PROVIDER_ENV = {
    "openai": ("openai", "OPENAI_API_KEY"),
    "openai_compatible": ("openai_compatible", "OPENAI_COMPATIBLE_API_KEY"),
    "anthropic": ("anthropic", "ANTHROPIC_API_KEY"),
    "gemini": ("google", "GOOGLE_API_KEY"),
    "google": ("google", "GOOGLE_API_KEY"),
    "deepseek": ("deepseek", "DEEPSEEK_API_KEY"),
    "groq": ("groq", "GROQ_API_KEY"),
    "xai": ("xai", "XAI_API_KEY"),
}

_RUNNER_PATH = Path(__file__).resolve().parents[2] / "deep" / "runner.py"


class DeepAnalysisError(Exception):
    """Normalised, user-safe deep-mode failure."""


class DeepDebateAdapter:
    """Streams a multi-agent debate via the ``runner`` subprocess."""

    def __init__(self, pool: DeepJobPool | None = None) -> None:
        self._settings = get_settings()
        # Shared process-wide pool by default (see get_deep_pool docstring) —
        # a fresh DeepJobPool() per adapter instance would give each request
        # its own uncontended semaphores and silently defeat both the global
        # concurrency cap and the per-namespace serialisation lock (D5).
        self._pool = pool or get_deep_pool()

    async def stream(
        self,
        request: AnalysisRequest,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> AsyncIterator[AnalysisEvent]:
        async with ephemeral_secret(request.ai.api_key) as secret:
            async for event in self._stream(request, secret, namespace):
                yield event

    async def _stream(
        self,
        request: AnalysisRequest,
        secret,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> AsyncIterator[AnalysisEvent]:
        if not secret:
            raise DeepAnalysisError("an API key is required for deep analysis")
        key = secret.expose()
        model = request.ai.model.strip()
        if not model:
            raise DeepAnalysisError("a model name is required")

        provider = request.ai.provider.strip().lower()
        ta_provider, key_env = _PROVIDER_ENV.get(provider, (provider, None))
        if key_env is None:
            raise DeepAnalysisError(f"unsupported deep-mode provider: {provider}")

        data_dir = self._settings.data_dir
        memory_log_path = str(memory_log_path_for(namespace, data_dir))

        cfg = {
            "symbol": request.symbol,
            "provider": ta_provider,
            "model": model,
            "backend_url": request.ai.base_url or None,
            "output_language": request.output_language,
            "memory_log_path": memory_log_path,
            "data_cache_dir": str(Path(data_dir) / "cache"),
            "results_dir": str(Path(data_dir) / "results"),
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        }

        # Minimal env: PATH/HOME so Python subprocess runs, plus the single key.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            key_env: key,
        }

        async with self._pool.acquire(namespace):
            yield AnalysisEvent(
                type="status", message=f"Queued deep analysis for {request.symbol}…"
            )
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", str(_RUNNER_PATH),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            deadline = asyncio.get_event_loop().time() + self._settings.deep_runner_timeout_seconds
            try:
                assert proc.stdin is not None
                proc.stdin.write(json.dumps(cfg).encode())
                await proc.stdin.drain()
                proc.stdin.close()

                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        raise DeepAnalysisError(
                            f"deep analysis timed out after {self._settings.deep_runner_timeout_seconds}s"
                        )
                    try:
                        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                    except asyncio.TimeoutError as exc:
                        raise DeepAnalysisError(
                            f"deep analysis timed out after {self._settings.deep_runner_timeout_seconds}s"
                        ) from exc
                    if not raw:  # EOF — subprocess closed stdout
                        break
                    raw = raw.decode(errors="replace").strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    yield AnalysisEvent(
                        type=obj.get("type", "status"),
                        message=obj.get("message", ""),
                        data=obj.get("data"),
                    )

                returncode = await proc.wait()
                if returncode != 0:
                    stderr = (await proc.stderr.read()).decode(errors="replace")[:500]
                    raise DeepAnalysisError(
                        f"deep analysis failed (exit {returncode}){(': ' + stderr) if stderr else ''}"
                    )
            except asyncio.CancelledError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
                raise
            finally:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                    await proc.wait()