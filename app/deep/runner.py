"""Subprocess entrypoint for a single deep-mode (TradingAgents) analysis run.

Why a subprocess: TradingAgents keeps a module-level global ``_config`` dict
(``tradingagents/dataflows/config.py``) that is read mid-graph by many call
sites. Running one analysis per OS process sidesteps that shared mutable state
entirely — no source changes, and future upstream fixes stay pullable.

Contract (EXECUTION_PLAN.md C3 / C6 / D4):

- Reads a JSON config document from **stdin** (never the API key).
- Reads the provider API key only from this process's **env** (the provider's
  own env var, e.g. ``OPENAI_API_KEY``) — never argv, never a file.
- Builds a **full** config via ``deepcopy(DEFAULT_CONFIG)`` + overrides (a
  partial dict will ``KeyError`` inside ``TradingAgentsGraph.__init__``).
- Keeps ``checkpoint_enabled=False`` (avoids per-ticker SQLite collisions).
- Streams one NDJSON line per event to stdout, ending with a ``final`` event.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy

# This process is spawned with a minimal env, so guard the heavy import: it is
# only attempted once we actually need TradingAgents (real deep runs).
try:
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.analyst_execution import (
        AnalystWallTimeTracker,
        build_analyst_execution_plan,
        sync_analyst_tracker_from_chunk,
    )
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    _TRADINGAGENTS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on install context
    _TRADINGAGENTS_AVAILABLE = False


# mindmesh provider -> TradingAgents provider. Gemini is "google" upstream.
_PROVIDER_MAP = {
    "openai": "openai",
    "openai_compatible": "openai_compatible",
    "anthropic": "anthropic",
    "gemini": "google",
    "google": "google",
}

ANALYST_ORDER = ["market", "social", "news", "fundamentals"]

_SECTION_TITLES = {
    "market_report": "Market Analysis",
    "sentiment_report": "Sentiment Analysis",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}


def _emit(event_type: str, message: str = "", data: dict | None = None) -> None:
    line = json.dumps({"type": event_type, "message": message, "data": data}, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _map_provider(provider: str) -> str:
    return _PROVIDER_MAP.get(provider.strip().lower(), provider.strip().lower())


def _build_full_config(cfg: dict) -> dict:
    """deepcopy(DEFAULT_CONFIG) + overrides, so the graph never sees a partial dict."""
    config = deepcopy(DEFAULT_CONFIG)
    config["llm_provider"] = _map_provider(cfg.get("provider", "openai"))
    model = cfg.get("model") or ""
    config["deep_think_llm"] = cfg.get("deep_think_llm") or model
    config["quick_think_llm"] = cfg.get("quick_think_llm") or model
    if cfg.get("backend_url"):
        config["backend_url"] = cfg["backend_url"]
    config["output_language"] = cfg.get("output_language", "English")
    config["checkpoint_enabled"] = False  # EXECUTION_PLAN.md D6 — never enable for web use

    if cfg.get("memory_log_path"):
        config["memory_log_path"] = cfg["memory_log_path"]
    if cfg.get("data_cache_dir"):
        config["data_cache_dir"] = cfg["data_cache_dir"]
    if cfg.get("results_dir"):
        config["results_dir"] = cfg["results_dir"]
    if cfg.get("max_debate_rounds") is not None:
        config["max_debate_rounds"] = int(cfg["max_debate_rounds"])
    if cfg.get("max_risk_discuss_rounds") is not None:
        config["max_risk_discuss_rounds"] = int(cfg["max_risk_discuss_rounds"])
    return config


def _merge_chunks(trace: list[dict]) -> dict:
    final_state: dict = {}
    for chunk in trace:
        final_state.update(chunk)
    return final_state


def _invoke_streaming(graph: TradingAgentsGraph, init_state: dict, args: dict):
    """Yield per-node delta chunks from graph.graph.stream (CLI pattern)."""
    return graph.graph.stream(init_state, **args)


def _extract_final_report(final_state: dict) -> dict:
    """Collapse the full run state into the bull/bear/risk debate structure."""
    debate = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    return {
        "symbol": final_state.get("company_of_interest"),
        "trade_date": final_state.get("trade_date"),
        "market_report": final_state.get("market_report"),
        "sentiment_report": final_state.get("sentiment_report"),
        "news_report": final_state.get("news_report"),
        "fundamentals_report": final_state.get("fundamentals_report"),
        "investment_debate_state": {
            "bull_history": debate.get("bull_history"),
            "bear_history": debate.get("bear_history"),
            "judge_decision": debate.get("judge_decision"),
        },
        "trader_investment_plan": final_state.get("trader_investment_plan"),
        "risk_debate_state": {
            "aggressive_history": risk.get("aggressive_history"),
            "conservative_history": risk.get("conservative_history"),
            "neutral_history": risk.get("neutral_history"),
            "judge_decision": risk.get("judge_decision"),
        },
        "final_trade_decision": final_state.get("final_trade_decision"),
    }


def _run(cfg: dict) -> int:
    if not _TRADINGAGENTS_AVAILABLE:
        _emit("error", "tradingagents is not installed in this environment")
        return 2

    # Test/verification hook: emit the config this process *would* build and
    # exit. Lets the concurrency test prove two simultaneous subprocesses each
    # hold their own independent config (the process-isolation fix for the
    # framework's module-global `_config`). No provider key is read or emitted.
    if cfg.get("echo_config"):
        built = _build_full_config(cfg)
        _emit(
            "final",
            "config",
            data={
                "llm_provider": built["llm_provider"],
                "deep_think_llm": built["deep_think_llm"],
                "quick_think_llm": built["quick_think_llm"],
                "output_language": built["output_language"],
                "backend_url": built.get("backend_url"),
                "checkpoint_enabled": built["checkpoint_enabled"],
                "memory_log_path": built.get("memory_log_path"),
            },
        )
        return 0

    provider = _map_provider(cfg.get("provider", "openai"))
    key_env = get_api_key_env(provider)
    if key_env:
        import os
        if not os.environ.get(key_env):
            _emit("error", f"missing {key_env} in runner environment")
            return 2

    symbol = cfg["symbol"]
    trade_date = cfg.get("trade_date") or None
    if not trade_date:
        from datetime import datetime
        trade_date = datetime.now().strftime("%Y-%m-%d")
    asset_type = cfg.get("asset_type", "stock")
    selected_analysts = cfg.get("selected_analysts") or list(ANALYST_ORDER)
    selected_analysts = [a for a in ANALYST_ORDER if a in selected_analysts] or list(ANALYST_ORDER)

    config = _build_full_config(cfg)

    _emit("status", f"Starting deep analysis for {symbol} ({provider})")

    try:
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=config,
            debug=True,
        )
    except Exception as exc:
        _emit("error", f"graph construction failed: {exc.__class__.__name__}")
        return 2

    plan = build_analyst_execution_plan(selected_analysts)
    tracker = AnalystWallTimeTracker(plan)

    # Mirror _run_graph's memory + instrument context injection so the
    # namespaced reflection log is actually read and written (EXECUTION_PLAN.md D5).
    past_context = graph.memory_log.get_past_context(symbol)
    try:
        instrument_context = graph.resolve_instrument_context(symbol, asset_type)
    except Exception:
        instrument_context = ""

    init_state = graph.propagator.create_initial_state(
        symbol, trade_date, asset_type=asset_type,
        past_context=past_context, instrument_context=instrument_context,
    )
    args = graph.propagator.get_graph_args()

    trace: list[dict] = []
    seen_sections: set[str] = set()
    try:
        for chunk in _invoke_streaming(graph, init_state, args):
            trace.append(chunk)
            sync_analyst_tracker_from_chunk(tracker, chunk)

            for section in (
                "market_report", "sentiment_report", "news_report", "fundamentals_report",
                "investment_debate_state", "trader_investment_plan", "risk_debate_state",
            ):
                value = chunk.get(section)
                if value and section not in seen_sections:
                    seen_sections.add(section)
                    _emit("status", _SECTION_TITLES.get(section, section))
    except Exception as exc:
        _emit("error", f"analysis failed: {exc.__class__.__name__}")
        return 2

    final_state = _merge_chunks(trace)

    if not final_state.get("final_trade_decision"):
        _emit("error", "analysis produced no final decision")
        return 2

    # Persist the decision to the namespaced memory log for reflection.
    try:
        graph.memory_log.store_decision(
            ticker=symbol, trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )
    except Exception:
        pass  # memory log is best-effort; a failure must not fail the run

    _emit("final", "Analysis complete", data=_extract_final_report(final_state))
    return 0


def main() -> int:
    payload = sys.stdin.read()
    try:
        cfg = json.loads(payload) if payload.strip() else {}
    except json.JSONDecodeError as exc:
        _emit("error", f"invalid stdin JSON: {exc}")
        return 2

    if not cfg.get("symbol"):
        _emit("error", "missing symbol in runner config")
        return 2

    try:
        return _run(cfg)
    except Exception as exc:  # top-level safety net
        _emit("error", f"{exc.__class__.__name__}")
        return 2


if __name__ == "__main__":
    sys.exit(main())