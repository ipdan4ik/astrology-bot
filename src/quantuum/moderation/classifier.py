from __future__ import annotations

from quantuum.moderation.policy import Category, Safe, Tier1Hit

# Precedence: most severe → least. Returned at the first match.
_TIER1_PRECEDENCE: list[tuple[Category, tuple[str, ...]]] = [
    (Category.SEXUAL_MINORS, ("sexual_minors",)),
    (Category.SELF_HARM, ("self_harm", "self_harm_intent", "self_harm_instructions")),
    (Category.VIOLENCE, ("violence", "violence_graphic")),
    (Category.HATE, ("hate", "hate_threatening")),
]


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
