from dataclasses import dataclass
from enum import Enum
from typing import TypedDict


class Category(str, Enum):
    SELF_HARM = "self_harm"
    VIOLENCE = "violence"
    SEXUAL_MINORS = "sexual_minors"
    HATE = "hate"
    MEDICAL_ADVICE = "medical_advice"
    LEGAL_ADVICE = "legal_advice"


class Action(str, Enum):
    SOFT_REDIRECT = "soft_redirect"
    HARD_BLOCK = "hard_block"


class Tier(str, Enum):
    ONE = "tier_1"  # safety (OpenAI Moderation)
    TWO = "tier_2"  # out-of-scope advice (mini-LLM)


class PolicyEntry(TypedDict):
    action: Action
    tier: Tier
    i18n_key: str
    uses_helpline: bool


POLICY: dict[Category, PolicyEntry] = {
    Category.SELF_HARM: {
        "action": Action.SOFT_REDIRECT,
        "tier": Tier.ONE,
        "i18n_key": "moderation.self_harm",
        "uses_helpline": True,
    },
    Category.VIOLENCE: {
        "action": Action.HARD_BLOCK,
        "tier": Tier.ONE,
        "i18n_key": "moderation.violence",
        "uses_helpline": False,
    },
    Category.SEXUAL_MINORS: {
        "action": Action.HARD_BLOCK,
        "tier": Tier.ONE,
        "i18n_key": "moderation.blocked_generic",
        "uses_helpline": False,
    },
    Category.HATE: {
        "action": Action.SOFT_REDIRECT,
        "tier": Tier.ONE,
        "i18n_key": "moderation.hate",
        "uses_helpline": False,
    },
    Category.MEDICAL_ADVICE: {
        "action": Action.SOFT_REDIRECT,
        "tier": Tier.TWO,
        "i18n_key": "moderation.medical",
        "uses_helpline": False,
    },
    Category.LEGAL_ADVICE: {
        "action": Action.SOFT_REDIRECT,
        "tier": Tier.TWO,
        "i18n_key": "moderation.legal",
        "uses_helpline": False,
    },
}


@dataclass(frozen=True)
class Safe:
    pass


@dataclass(frozen=True)
class Tier1Hit:
    category: Category


@dataclass(frozen=True)
class Tier2Hit:
    category: Category


ModerationVerdict = Safe | Tier1Hit | Tier2Hit
