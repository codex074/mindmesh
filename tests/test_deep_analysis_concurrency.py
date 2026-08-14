"""The key concurrency test (EXECUTION_PLAN.md C8 / Verification plan).

Exercises the process-isolation fix for TradingAgents' module-global ``_config``:
two runner subprocesses start simultaneously with **different** output languages,
providers, and models; each emitted config must reflect its own request.

It also verifies the per-namespace scheduling rules: same-namespace jobs
serialize; different-namespace jobs run in parallel under the global cap.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "app" / "deep" / "runner.py"


def _run_echo(cfg: dict) -> dict:
    """Run the runner subprocess with `echo_config` and return the emitted config."""
    import subprocess

    completed = subprocess.run(
        [sys.executable, "-u", str(RUNNER)],
        input=json.dumps({**cfg, "echo_config": True}),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    out = [json.loads(line) for line in completed.stdout.strip().splitlines() if line.strip()]
    final = [o for o in out if o["type"] == "final"][0]
    return final["data"]


def test_two_simultaneous_runners_keep_independent_configs():
    """Different language/provider/model in two parallel subprocesses must not leak."""
    cfgs = [
        {
            "symbol": "AAPL",
            "provider": "openai",
            "model": "gpt-model-a",
            "output_language": "English",
        },
        {
            "symbol": "MSFT",
            "provider": "anthropic",
            "model": "claude-model-b",
            "output_language": "Thai",
        },
    ]

    async def run_one():
        import subprocess

        async def spawn(cfg):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", str(RUNNER),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate(json.dumps({**cfg, "echo_config": True}).encode())
            assert proc.returncode == 0, err.decode()
            parsed = [json.loads(l) for l in out.decode().strip().splitlines() if l.strip()]
            return [p for p in parsed if p["type"] == "final"][0]["data"]

        return await asyncio.gather(spawn(cfgs[0]), spawn(cfgs[1]))

    results = asyncio.run(run_one())

    by_provider = {r["llm_provider"]: r for r in results}
    # Distinct providers means each subprocess built its own config in isolation.
    assert set(by_provider) == {"openai", "anthropic"}

    assert by_provider["openai"]["output_language"] == "English"
    assert by_provider["openai"]["deep_think_llm"] == "gpt-model-a"
    assert by_provider["anthropic"]["output_language"] == "Thai"
    assert by_provider["anthropic"]["deep_think_llm"] == "claude-model-b"


def test_runner_config_never_partial_and_checkpoint_off():
    """The config emitted by a runner is complete and checkpointing stays off (D6)."""
    emitted = _run_echo({
        "symbol": "AAPL",
        "provider": "openai",
        "model": "gpt-test",
        "output_language": "English",
        "memory_log_path": "/tmp/test_memory.md",
    })
    # checkpoint_enabled must be False even though it isn't in the input config.
    assert emitted["checkpoint_enabled"] is False
    assert emitted["llm_provider"] == "openai"
    assert emitted["deep_think_llm"] == "gpt-test"
    assert emitted["quick_think_llm"] == "gpt-test"
    assert emitted["memory_log_path"] == "/tmp/test_memory.md"


def test_same_namespace_serializes():
    """Same-namespace jobs never run concurrently (per-namespace cap = 1)."""
    from app.deep.pool import DeepJobPool

    async def scenario():
        pool = DeepJobPool(max_concurrent_jobs=3, per_namespace=1)
        active = 0
        max_active = 0

        async def job():
            nonlocal active, max_active
            async with pool.acquire("alice"):
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1

        await asyncio.gather(job(), job(), job())
        return max_active

    assert asyncio.run(scenario()) == 1


def test_adapter_default_pool_is_shared_singleton():
    """Two adapters built the normal way (no explicit pool) MUST share one pool.

    This is what makes the per-namespace lock and global cap apply across real
    HTTP requests: `stream_analysis()` constructs a fresh `DeepDebateAdapter()`
    per call, so if each adapter got its own `DeepJobPool()`, two concurrent
    requests from the same user would each get an uncontended semaphore and
    never actually serialise (the bug this test guards against).
    """
    from app.analysis.adapters.deep_debate import DeepDebateAdapter
    from app.deep.pool import get_deep_pool

    a = DeepDebateAdapter()
    b = DeepDebateAdapter()
    assert a._pool is b._pool
    assert a._pool is get_deep_pool()


def test_different_namespaces_run_in_parallel():
    """Different users run in true parallel up to the global cap."""
    from app.deep.pool import DeepJobPool

    async def scenario():
        pool = DeepJobPool(max_concurrent_jobs=3, per_namespace=1)
        active = 0
        max_active = 0

        async def job(ns):
            nonlocal active, max_active
            async with pool.acquire(ns):
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1

        await asyncio.gather(job("alice"), job("bob"), job("carol"))
        return max_active

    assert asyncio.run(scenario()) == 3