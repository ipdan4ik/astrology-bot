from __future__ import annotations

# Additional providers can be added here with extra elif branches.
# YAGNI: only openai is implemented now.


def get_llm_client(settings) -> "LLMClient | None":  # noqa: F821
    if settings.llm_provider == "openai" and settings.llm_api_key:
        from quantuum.llm.openai_client import OpenAIClient

        return OpenAIClient(api_key=settings.llm_api_key)
    return None
