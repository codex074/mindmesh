"""Quick-mode DeepSeek adapter (PRODUCT_PLAN.md §3.3).

DeepSeek exposes an OpenAI-compatible Chat Completions API, so this is a thin
subclass of the generic adapter that pins the default base URL. A user-supplied
``base_url`` still takes precedence and passes the SSRF guard like any custom
endpoint.
"""

from __future__ import annotations

from app.analysis.adapters.openai_compatible import QuickOpenAICompatibleAdapter


class DeepSeekAdapter(QuickOpenAICompatibleAdapter):
    """OpenAI-compatible adapter fixed to DeepSeek's public endpoint."""

    default_base_url = "https://api.deepseek.com"


def create_adapter() -> DeepSeekAdapter:
    return DeepSeekAdapter()