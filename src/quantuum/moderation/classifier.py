from __future__ import annotations

from quantuum.moderation.policy import Category, Safe, Tier1Hit, Tier2Hit

# Precedence: most severe → least. Returned at the first match.
_TIER1_PRECEDENCE: list[tuple[Category, tuple[str, ...]]] = [
    (Category.SEXUAL_MINORS, ("sexual_minors",)),
    (Category.SELF_HARM, ("self_harm", "self_harm_intent", "self_harm_instructions")),
    (Category.VIOLENCE, ("violence", "violence_graphic")),
    (Category.HATE, ("hate", "hate_threatening")),
]


import json as _json
from pathlib import Path as _Path

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
