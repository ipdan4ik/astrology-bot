from __future__ import annotations

import asyncio
import json as _json
from pathlib import Path as _Path

from quantuum.logging_setup import get_logger as _get_logger
from quantuum.moderation.policy import Category, Safe, Tier1Hit, Tier2Hit

# Precedence: most severe → least. Returned at the first match.
_TIER1_PRECEDENCE: list[tuple[Category, tuple[str, ...]]] = [
    (Category.SEXUAL_MINORS, ("sexual_minors",)),
    (Category.SELF_HARM, ("self_harm", "self_harm_intent", "self_harm_instructions")),
    (Category.VIOLENCE, ("violence", "violence_graphic")),
    (Category.HATE, ("hate", "hate_threatening")),
]

_ADVICE_PROMPT_PATH = _Path(__file__).parent / "prompts" / "advice_classifier.txt"

_TIER2_BY_NAME: dict[str, Category] = {
    "medical": Category.MEDICAL_ADVICE,
    "legal": Category.LEGAL_ADVICE,
}


async def _llm_advice_classifier(
    text: str,
    lang: str,
    client,
    *,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 32,
) -> Safe | Tier2Hit:
    """Classify whether a question is out-of-scope advice (medical/legal).

    Returns Safe on any parse/format/unknown-category failure (fail-open).
    Caller is responsible for catching client-level exceptions.
    """
    system = _ADVICE_PROMPT_PATH.read_text()
    user = f"User question ({lang}):\n{text}"
    result = await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    try:
        payload = _json.loads(result.text.strip())
    except (ValueError, TypeError):
        return Safe()
    cat_name = payload.get("category")
    category = _TIER2_BY_NAME.get(cat_name) if isinstance(cat_name, str) else None
    return Tier2Hit(category=category) if category else Safe()


async def _openai_moderate(text: str, client, *, model: str) -> Safe | Tier1Hit:
    """Run OpenAI Moderation API and map to a Tier1 verdict.

    Caller is responsible for catching exceptions and applying fail-open.
    """
    resp = await client.moderations.create(model=model, input=text)
    cats = resp.results[0].categories
    for category, attr_names in _TIER1_PRECEDENCE:
        if any(getattr(cats, name, False) for name in attr_names):
            return Tier1Hit(category=category)
    return Safe()


_log = _get_logger("moderation")


async def moderate(
    text: str,
    lang: str,
    *,
    openai_client,
    llm_client,
    settings,
) -> Safe | Tier1Hit | Tier2Hit:
    """Run Tier1 (OpenAI Moderation) and Tier2 (LLM advice classifier) in parallel.

    Safety (Tier1) wins over scope (Tier2). Kill switch and fail-open are honored
    via settings. Caller passes raw clients so tests can stub them.
    """
    if not settings.moderation_enabled:
        _log.info("moderation.disabled")
        return Safe()

    advice_model = settings.moderation_advice_model or settings.llm_model

    tier1_coro = _openai_moderate(text, openai_client, model=settings.moderation_openai_model)
    tier2_coro = _llm_advice_classifier(
        text,
        lang,
        llm_client,
        model=advice_model,
        temperature=settings.moderation_advice_temperature,
        max_tokens=settings.moderation_advice_max_tokens,
    )
    results = await asyncio.gather(tier1_coro, tier2_coro, return_exceptions=True)
    tier1, tier2 = results

    if isinstance(tier1, Exception):
        _log.warning("moderation.api_error", provider="openai", error=str(tier1))
        if not settings.moderation_fail_open:
            raise tier1
        tier1 = Safe()
    if isinstance(tier2, Exception):
        _log.warning("moderation.api_error", provider="mini_llm", error=str(tier2))
        if not settings.moderation_fail_open:
            raise tier2
        tier2 = Safe()

    if isinstance(tier1, Tier1Hit):
        return tier1
    if isinstance(tier2, Tier2Hit):
        return tier2
    return Safe()
