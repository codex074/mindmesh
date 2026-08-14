"""AI Analysis module — the single locked ``stream_analysis`` seam
(PRODUCT_PLAN.md §6.2 / EXECUTION_PLAN.md C7).

Routes and UI only ever call this one function. ``analysis_mode`` selects the
adapter: ``"quick"`` → in-process single-model adapter, ``"deep"`` →
subprocess-backed TradingAgents debate adapter. Per-user namespacing for deep
mode is an optional argument so the route can pass the proxy-auth identity
without the rest of the app knowing any mode is subprocess-backed.
"""

from __future__ import annotations

from typing import AsyncIterator

from app.analysis.adapters.anthropic import AnthropicAdapter
from app.analysis.adapters.deep_debate import DeepDebateAdapter
from app.analysis.adapters.deepseek import DeepSeekAdapter
from app.analysis.adapters.gemini import GeminiAdapter
from app.analysis.adapters.openai_compatible import QuickOpenAICompatibleAdapter
from app.analysis.models import AnalysisEvent, AnalysisMode, AnalysisRequest
from app.deep.namespace import DEFAULT_NAMESPACE


class UnsupportedModeError(Exception):
    pass


class UnsupportedProviderError(Exception):
    pass


_QUICK_FACTORIES = {
    "openai_compatible": QuickOpenAICompatibleAdapter,
    "openai": QuickOpenAICompatibleAdapter,
    "deepseek": DeepSeekAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "google": GeminiAdapter,
}


async def stream_analysis(
    request: AnalysisRequest,
    namespace: str = DEFAULT_NAMESPACE,
) -> AsyncIterator[AnalysisEvent]:
    """Dispatch to the adapter selected by ``request.analysis_mode``."""
    if request.analysis_mode == AnalysisMode.QUICK:
        factory = _QUICK_FACTORIES.get(request.ai.provider.strip().lower())
        if factory is None:
            raise UnsupportedProviderError(request.ai.provider)
        adapter = factory()
        async for event in adapter.stream(request):
            yield event
        return

    if request.analysis_mode == AnalysisMode.DEEP:
        adapter = DeepDebateAdapter()
        async for event in adapter.stream(request, namespace=namespace):
            yield event
        return

    raise UnsupportedModeError(request.analysis_mode.value)