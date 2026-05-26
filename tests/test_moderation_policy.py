from quantuum.moderation.policy import (
    Action,
    Category,
    POLICY,
    Safe,
    Tier,
    Tier1Hit,
    Tier2Hit,
)


def test_category_enum_values():
    assert Category.SELF_HARM.value == "self_harm"
    assert Category.VIOLENCE.value == "violence"
    assert Category.SEXUAL_MINORS.value == "sexual_minors"
    assert Category.HATE.value == "hate"
    assert Category.MEDICAL_ADVICE.value == "medical_advice"
    assert Category.LEGAL_ADVICE.value == "legal_advice"


def test_action_enum_values():
    assert Action.SOFT_REDIRECT.value == "soft_redirect"
    assert Action.HARD_BLOCK.value == "hard_block"


def test_policy_maps_every_category():
    for cat in Category:
        entry = POLICY[cat]
        assert entry["action"] in (Action.SOFT_REDIRECT, Action.HARD_BLOCK)
        assert entry["tier"] in (Tier.ONE, Tier.TWO)
        assert entry["i18n_key"].startswith("moderation.")


def test_policy_self_harm_entry():
    assert POLICY[Category.SELF_HARM]["i18n_key"] == "moderation.self_harm"
    assert POLICY[Category.SELF_HARM]["uses_helpline"] is True


def test_verdict_dataclasses():
    safe = Safe()
    hit1 = Tier1Hit(category=Category.SELF_HARM)
    hit2 = Tier2Hit(category=Category.MEDICAL_ADVICE)
    assert hit1.category is Category.SELF_HARM
    assert hit2.category is Category.MEDICAL_ADVICE
    assert hit1 != safe
    assert hit2 != safe
