"""TradingView Desktop bridge — LOCAL-ONLY (additive to app/market/tradingview.py).

Reads indicator values, INCLUDING the user's own custom Pine Script
indicators, off a live TradingView Desktop instance running on this same
host. This is fundamentally different from app/market/tradingview.py (the
public TradingView "Technicals" scanner, which only ever sees TradingView's
built-in default indicator set and works from any VPS): this module can only
work where TradingView Desktop is open, logged in, and reachable over Chrome
DevTools Protocol on the same machine as this process.

It works by spawning the existing, separately-installed `tradingview-mcp`
Node.js server (which already implements the CDP automation) and talking to
it as an MCP client — reusing that tested bridge instead of re-implementing
CDP scraping here. Requires the optional `desktop` extra
(`pip install -e ".[desktop]"`) for the `mcp` client library, and Node.js on
PATH. Disabled by default (APP_MARKET_TV_DESKTOP_ENABLED=false).

Two constraints shape this module's design, both found by exercising it
against a real TradingView Desktop, not just by inspection:

1. The chart is one shared UI resource, so "switch symbol, then read its
   indicators" must run as one uninterrupted sequence — otherwise a second
   request's chart_set_symbol can land between the first request's switch
   and its read, and each request reads back the other's data. A plain
   asyncio.Lock held for the whole sequence (not per RPC) fixes this.
2. The mcp SDK's session/stdio transport uses anyio cancel scopes, which
   MUST be entered and exited by the same asyncio Task. Wrapping the
   session's lazy creation in asyncio.wait_for (to bound total request
   time) runs that creation inside wait_for's own internal task — so a
   later close from a different task (e.g. app shutdown) raises
   "Attempted to exit cancel scope in a different task than it was entered
   in" and the subprocess is never reaped. The fix is a single dedicated
   worker task that owns the session for its entire lifetime: it enters the
   session once and is the only task that ever tears it down. Callers talk
   to it through a queue and never touch the session directly, so wrapping
   *their* side in wait_for is safe.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from datetime import datetime, timezone

from .models import DesktopIndicatorSnapshot, DesktopStudy

# How long to poll chart_get_state for the requested symbol to take effect
# before reading indicator values, and how long to then let indicators settle.
_SYMBOL_SWITCH_POLL_ATTEMPTS = 10
_SYMBOL_SWITCH_POLL_INTERVAL_SECONDS = 0.3
_SYMBOL_SWITCH_SETTLE_SECONDS = 0.5

_SHUTDOWN = object()  # queue sentinel


class TradingViewDesktopError(Exception):
    """Normalised, user-safe TradingView Desktop bridge failure."""


class TradingViewDesktopUnavailableError(TradingViewDesktopError):
    """The bridge is disabled, misconfigured, or its optional dependency is missing."""


class TradingViewDesktopBridgeError(TradingViewDesktopError):
    """The bridge is configured but the underlying tool call failed
    (Desktop not open, CDP disconnected, or a tool-level error)."""


class TradingViewDesktopTimeoutError(TradingViewDesktopBridgeError):
    """The end-to-end switch+read operation exceeded its overall budget."""


def _base_symbol(value: str) -> str:
    """The ticker portion of an EXCHANGE:SYMBOL string (or the whole string
    if there's no prefix), uppercased. Used for exact-match comparison —
    never substring containment, which false-positives whenever one ticker
    happens to be a substring of another (e.g. "MU" inside "NASDAQ:AMUZN")."""
    return value.rsplit(":", 1)[-1].strip().upper()


def _symbol_matches(requested: str, chart_symbol: str) -> bool:
    return _base_symbol(requested) == _base_symbol(chart_symbol)


class _DesktopBridge:
    """A single worker task owns the MCP session end-to-end (see module
    docstring for why). Request tasks never touch the session; they submit
    (tool name, arguments) pairs through a queue and await a future for the
    result. ``lock`` is a plain asyncio.Lock — safe to hold across whatever
    task a caller happens to be in — used by callers to serialise a whole
    multi-call sequence (switch + poll + read) against other callers.
    """

    def __init__(self, command: str, args: list[str], timeout: float) -> None:
        self._command = command
        self._args = args
        self._timeout = timeout
        self.lock = asyncio.Lock()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    def _ensure_worker(self) -> asyncio.Task:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())
        return self._worker

    async def _run(self) -> None:
        """The worker task's entire body. Everything that touches the mcp
        session — creation, calls, and teardown — happens here, in this one
        task, satisfying anyio's cancel-scope task affinity."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            await self._drain_with_error(
                TradingViewDesktopUnavailableError(
                    "the 'mcp' package is not installed — install with pip install -e \".[desktop]\""
                )
            )
            return

        try:
            async with AsyncExitStack() as stack:
                params = StdioServerParameters(command=self._command, args=self._args)
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                while True:
                    item = await self._queue.get()
                    if item is _SHUTDOWN:
                        return
                    name, arguments, future = item
                    if future.cancelled():
                        continue
                    try:
                        payload = await asyncio.wait_for(
                            self._call_and_parse(session, name, arguments), timeout=self._timeout
                        )
                    except Exception as exc:  # noqa: BLE001 — reported to the caller, not raised here
                        if not future.cancelled():
                            future.set_exception(
                                exc if isinstance(exc, TradingViewDesktopError)
                                else TradingViewDesktopBridgeError(
                                    f"desktop bridge call to {name} failed: {exc.__class__.__name__}"
                                )
                            )
                        # A wedged CDP connection likely won't recover — stop
                        # this worker so the next call spawns a fresh one.
                        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                            return
                    else:
                        if not future.cancelled():
                            future.set_result(payload)
        except Exception as exc:  # session creation itself failed
            await self._drain_with_error(
                TradingViewDesktopBridgeError(f"desktop bridge session failed: {exc.__class__.__name__}")
            )

    async def _drain_with_error(self, exc: Exception) -> None:
        """Fail whatever's already queued, and anything queued for a short
        grace period after — a burst of near-simultaneous callers can enqueue
        while the worker is still starting up and failing."""
        deadline = asyncio.get_event_loop().time() + 0.1
        while True:
            try:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return
                item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return
            if item is _SHUTDOWN:
                return
            _, _, future = item
            if not future.cancelled():
                future.set_exception(exc)

    @staticmethod
    async def _call_and_parse(session, name: str, arguments: dict) -> dict:
        result = await session.call_tool(name, arguments)
        text = next(
            (block.text for block in result.content if getattr(block, "type", None) == "text"),
            None,
        )
        if text is None:
            raise TradingViewDesktopBridgeError(f"desktop tool {name} returned no text content")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TradingViewDesktopBridgeError(f"desktop tool {name} returned invalid JSON") from exc

        if result.isError or payload.get("success") is False:
            raise TradingViewDesktopBridgeError(
                f"desktop tool {name} error: {payload.get('error', text)[:200]}"
            )
        return payload

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self._ensure_worker()
        future = asyncio.get_event_loop().create_future()
        await self._queue.put((name, arguments, future))
        return await future

    async def close(self) -> None:
        worker = self._worker
        if worker is None:
            return
        if not worker.done():
            await self._queue.put(_SHUTDOWN)
        await worker


_bridge: _DesktopBridge | None = None


def _get_bridge() -> _DesktopBridge:
    global _bridge
    from app.config import get_settings

    settings = get_settings()
    if not settings.market_tv_desktop_enabled:
        raise TradingViewDesktopUnavailableError(
            "the TradingView Desktop bridge is disabled "
            "(set APP_MARKET_TV_DESKTOP_ENABLED=true and APP_MARKET_TV_DESKTOP_SERVER_PATH; "
            "local-only, requires TradingView Desktop open on this host)"
        )
    if not settings.market_tv_desktop_server_path:
        raise TradingViewDesktopUnavailableError("APP_MARKET_TV_DESKTOP_SERVER_PATH is not set")

    if _bridge is None:
        _bridge = _DesktopBridge(
            command="node",
            args=[settings.market_tv_desktop_server_path],
            timeout=settings.market_tv_desktop_timeout_seconds,
        )
    return _bridge


async def close_bridge() -> None:
    """Tear down the persistent bridge connection and its Node subprocess.
    Call this from the app's shutdown hook — otherwise the spawned process
    outlives the FastAPI process (it has no parent-death signal of its own)
    and leaks a standing CDP connection to TradingView Desktop."""
    global _bridge
    bridge, _bridge = _bridge, None
    if bridge is not None:
        await bridge.close()


async def _switch_symbol_and_read(bridge: _DesktopBridge, symbol: str | None) -> tuple[dict, dict]:
    """Caller must hold ``bridge.lock``. Switches the chart (if a symbol is
    given) and reads indicator values as one uninterrupted sequence, so no
    other request's chart_set_symbol can land in between."""
    if symbol:
        await bridge.call_tool("chart_set_symbol", {"symbol": symbol})
        state = await bridge.call_tool("chart_get_state", {})
        for _ in range(_SYMBOL_SWITCH_POLL_ATTEMPTS):
            if _symbol_matches(symbol, state.get("symbol", "")):
                break
            await asyncio.sleep(_SYMBOL_SWITCH_POLL_INTERVAL_SECONDS)
            state = await bridge.call_tool("chart_get_state", {})
        await asyncio.sleep(_SYMBOL_SWITCH_SETTLE_SECONDS)
    else:
        state = await bridge.call_tool("chart_get_state", {})

    values = await bridge.call_tool("data_get_study_values", {})
    return state, values


async def get_desktop_indicator_snapshot(symbol: str | None = None) -> DesktopIndicatorSnapshot:
    """Read current indicator values (including custom Pine indicators) off
    the live TradingView Desktop chart. If `symbol` is given and differs from
    the chart's current symbol, switches the chart first — this mutates the
    shared Desktop chart's visible symbol as a side effect. The whole
    operation is bounded by market_tv_desktop_timeout_seconds and runs under
    a single lock acquisition so it can't interleave with another request.
    Safe to wrap in asyncio.wait_for from any caller task: this function
    never enters the mcp session's cancel scopes itself (see module
    docstring) — only the dedicated worker task inside _DesktopBridge does."""
    from app.config import get_settings

    bridge = _get_bridge()
    settings = get_settings()

    async def _locked_read() -> tuple[dict, dict]:
        async with bridge.lock:
            return await _switch_symbol_and_read(bridge, symbol)

    try:
        state, values = await asyncio.wait_for(
            _locked_read(), timeout=settings.market_tv_desktop_timeout_seconds
        )
    except (TradingViewDesktopUnavailableError, TradingViewDesktopBridgeError):
        raise
    except Exception as exc:
        raise TradingViewDesktopTimeoutError(
            f"desktop operation timed out or failed: {exc.__class__.__name__}"
        ) from exc

    studies = [
        DesktopStudy(name=study.get("name", ""), values=study.get("values", {}))
        for study in values.get("studies", [])
    ]
    confirmed = not symbol or _symbol_matches(symbol, state.get("symbol", ""))

    return DesktopIndicatorSnapshot(
        requested_symbol=(symbol or state.get("symbol", "")).strip().upper(),
        chart_symbol=state.get("symbol", ""),
        resolution=str(state.get("resolution", "")),
        as_of=datetime.now(timezone.utc).isoformat(),
        studies=studies,
        warnings=(
            [] if confirmed
            else ["requested symbol was not confirmed on the chart before reading indicators"]
        ),
    )
