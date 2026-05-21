from __future__ import annotations

# Future providers (e.g. openai) can be added here with additional elif branches.
# YAGNI: only anthropic is implemented now.


def get_llm_client(settings) -> "LLMClient | None":  # noqa: F821
    if settings.llm_provider == "anthropic" and settings.llm_api_key:
        from quantuum.llm.anthropic_client import AnthropicClient

        return AnthropicClient(api_key=settings.llm_api_key)
    return None
