# Content Moderation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-LLM content moderation for free-text QA input — block trigger topics with localized canonical responses; do not charge quota on a moderation hit.

**Architecture:** New `quantuum.moderation` package with `moderate(text, lang) → ModerationVerdict`. Runs OpenAI Moderation API + a mini-LLM advice classifier in parallel. Wired into `bot/handlers/qa.py::_submit` **before** `consume_quota`. Verdicts persist to a new `moderation_events` table (sha256 + 80-char preview; no cleartext).

**Tech Stack:** Python 3.13, SQLModel + Alembic, aiogram FSM, `openai` async client, pydantic-settings, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-27-content-moderation-design.md`

---

## File Structure

**Created:**
- `src/quantuum/moderation/__init__.py` — public re-exports (`moderate`, `Category`, `Action`, `Safe`, `Tier1Hit`, `Tier2Hit`)
- `src/quantuum/moderation/classifier.py` — `moderate()` coordinator + Tier1/Tier2 wrappers
- `src/quantuum/moderation/policy.py` — `Category`, `Action`, `Tier`, verdict dataclasses, category→action→i18n-key map
- `src/quantuum/moderation/prompts/advice_classifier.txt` — JSON-output classifier prompt
- `src/quantuum/domain/moderation.py` — `record_moderation_event()` DB writer
- `alembic/versions/d0e1f2a3b4c5_moderation_events.py` — migration
- `tests/test_moderation_policy.py`
- `tests/test_moderation_openai_tier1.py`
- `tests/test_moderation_advice_tier2.py`
- `tests/test_moderation_coordinator.py`
- `tests/test_moderation_events_db.py`
- `tests/test_qa_moderation_e2e.py`

**Modified:**
- `src/quantuum/settings.py` — add 6 `moderation_*` fields
- `src/quantuum/db/models.py` — add `ModerationEvent` SQLModel
- `src/quantuum/i18n/seed_strings.py` — add 7 keys with ru/en
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — add 7 keys
- `src/quantuum/bot/handlers/qa.py` — pre-check via `moderate()` before `consume_quota`

---

## Task 1: Settings — moderation knobs

**Files:**
- Modify: `src/quantuum/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings.py`:

```python
def test_moderation_settings_defaults():
    from quantuum.settings import Settings

    s = Settings(
        database_url="postgresql://x",
        redis_url="redis://x",
        jwt_signing_key="x",
    )
    assert s.moderation_enabled is True
    assert s.moderation_fail_open is True
    assert s.moderation_openai_model == "omni-moderation-latest"
    assert s.moderation_advice_model is None  # falls back to llm_model
    assert s.moderation_advice_max_tokens == 32
    assert s.moderation_advice_temperature == 0.0


def test_moderation_settings_env_override(monkeypatch):
    from quantuum.settings import Settings

    monkeypatch.setenv("MODERATION_ENABLED", "false")
    monkeypatch.setenv("MODERATION_ADVICE_MODEL", "gpt-4o-mini")
    s = Settings(
        database_url="postgresql://x",
        redis_url="redis://x",
        jwt_signing_key="x",
    )
    assert s.moderation_enabled is False
    assert s.moderation_advice_model == "gpt-4o-mini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py::test_moderation_settings_defaults -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'moderation_enabled'`

- [ ] **Step 3: Add the fields**

In `src/quantuum/settings.py`, inside `class Settings(BaseSettings):` add (after `llm_max_tokens`):

```python
    moderation_enabled: bool = True
    moderation_fail_open: bool = True
    moderation_openai_model: str = "omni-moderation-latest"
    moderation_advice_model: str | None = None
    moderation_advice_max_tokens: int = 32
    moderation_advice_temperature: float = 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS for both new tests, no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/settings.py tests/test_settings.py
git commit -m "feat(moderation): settings knobs (enabled, fail-open, models, gen params)"
```

---

## Task 2: Policy types — Category, Action, Verdict dataclasses

**Files:**
- Create: `src/quantuum/moderation/__init__.py`
- Create: `src/quantuum/moderation/policy.py`
- Test: `tests/test_moderation_policy.py`

- [ ] **Step 1: Write the failing test**

`tests/test_moderation_policy.py`:

```python
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


def test_policy_self_harm_uses_helpline():
    assert POLICY[Category.SELF_HARM]["i18n_key"] == "moderation.self_harm"
    assert POLICY[Category.SELF_HARM]["uses_helpline"] is True


def test_verdict_dataclasses():
    safe = Safe()
    hit1 = Tier1Hit(category=Category.SELF_HARM)
    hit2 = Tier2Hit(category=Category.MEDICAL_ADVICE)
    assert hit1.category is Category.SELF_HARM
    assert hit2.category is Category.MEDICAL_ADVICE
    assert hit1 != safe and hit2 != safe
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.moderation'`

- [ ] **Step 3: Create the policy module**

`src/quantuum/moderation/__init__.py`:

```python
from quantuum.moderation.policy import (
    Action,
    Category,
    ModerationVerdict,
    POLICY,
    Safe,
    Tier,
    Tier1Hit,
    Tier2Hit,
)

__all__ = [
    "Action",
    "Category",
    "ModerationVerdict",
    "POLICY",
    "Safe",
    "Tier",
    "Tier1Hit",
    "Tier2Hit",
]
```

`src/quantuum/moderation/policy.py`:

```python
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict, Union


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


ModerationVerdict = Union[Safe, Tier1Hit, Tier2Hit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_policy.py -v`
Expected: PASS, 5/5.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/moderation/__init__.py src/quantuum/moderation/policy.py tests/test_moderation_policy.py
git commit -m "feat(moderation): policy types (Category/Action/Tier/verdicts) + category→action map"
```

---

## Task 3: OpenAI Moderation wrapper (Tier1)

**Files:**
- Modify: `src/quantuum/moderation/classifier.py` (create)
- Test: `tests/test_moderation_openai_tier1.py`

- [ ] **Step 1: Write the failing test**

`tests/test_moderation_openai_tier1.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.moderation.classifier import _openai_moderate
from quantuum.moderation.policy import Category, Safe, Tier1Hit


def _mk_resp(*, self_harm=False, violence=False, sexual_minors=False, hate=False):
    cats = MagicMock()
    cats.self_harm = self_harm
    cats.self_harm_intent = self_harm
    cats.self_harm_instructions = self_harm
    cats.violence = violence
    cats.violence_graphic = violence
    cats.sexual_minors = sexual_minors
    cats.hate = hate
    cats.hate_threatening = hate

    result_obj = MagicMock()
    result_obj.categories = cats

    resp = MagicMock()
    resp.results = [result_obj]
    return resp


@pytest.mark.asyncio
async def test_tier1_safe_input_returns_safe():
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=_mk_resp())
    verdict = await _openai_moderate("what's my sun sign?", client, model="m")
    assert isinstance(verdict, Safe)


@pytest.mark.asyncio
async def test_tier1_self_harm_returns_tier1hit():
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=_mk_resp(self_harm=True))
    verdict = await _openai_moderate("text", client, model="m")
    assert isinstance(verdict, Tier1Hit)
    assert verdict.category is Category.SELF_HARM


@pytest.mark.asyncio
async def test_tier1_violence_returns_tier1hit():
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=_mk_resp(violence=True))
    verdict = await _openai_moderate("text", client, model="m")
    assert isinstance(verdict, Tier1Hit) and verdict.category is Category.VIOLENCE


@pytest.mark.asyncio
async def test_tier1_sexual_minors_returns_tier1hit():
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=_mk_resp(sexual_minors=True))
    verdict = await _openai_moderate("text", client, model="m")
    assert isinstance(verdict, Tier1Hit) and verdict.category is Category.SEXUAL_MINORS


@pytest.mark.asyncio
async def test_tier1_hate_returns_tier1hit():
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=_mk_resp(hate=True))
    verdict = await _openai_moderate("text", client, model="m")
    assert isinstance(verdict, Tier1Hit) and verdict.category is Category.HATE


@pytest.mark.asyncio
async def test_tier1_safety_wins_over_other_signals():
    client = MagicMock()
    client.moderations.create = AsyncMock(
        return_value=_mk_resp(self_harm=True, violence=True)
    )
    verdict = await _openai_moderate("text", client, model="m")
    # SEXUAL_MINORS > SELF_HARM > VIOLENCE > HATE; here self_harm takes precedence over violence.
    assert isinstance(verdict, Tier1Hit) and verdict.category is Category.SELF_HARM


@pytest.mark.asyncio
async def test_tier1_sexual_minors_wins_over_self_harm():
    client = MagicMock()
    client.moderations.create = AsyncMock(
        return_value=_mk_resp(sexual_minors=True, self_harm=True)
    )
    verdict = await _openai_moderate("text", client, model="m")
    assert isinstance(verdict, Tier1Hit) and verdict.category is Category.SEXUAL_MINORS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_openai_tier1.py -v`
Expected: FAIL with `ImportError: cannot import name '_openai_moderate' from 'quantuum.moderation.classifier'`

- [ ] **Step 3: Create the classifier module with `_openai_moderate`**

`src/quantuum/moderation/classifier.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_openai_tier1.py -v`
Expected: PASS, 7/7.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/moderation/classifier.py tests/test_moderation_openai_tier1.py
git commit -m "feat(moderation): Tier1 OpenAI Moderation wrapper with severity precedence"
```

---

## Task 4: Mini-LLM advice classifier (Tier2)

**Files:**
- Create: `src/quantuum/moderation/prompts/advice_classifier.txt`
- Modify: `src/quantuum/moderation/classifier.py`
- Test: `tests/test_moderation_advice_tier2.py`

- [ ] **Step 1: Create the prompt file**

`src/quantuum/moderation/prompts/advice_classifier.txt`:

```
You are a strict topic classifier for an astrology chatbot.

Your job: given a user's question, decide whether they are asking the bot for
PROFESSIONAL ADVICE that an astrology product must NOT give.

Categories:
- "medical": the user is asking for a clinical diagnosis, treatment, medication
  guidance, or any advice that should come from a licensed medical professional.
  Questions about general wellbeing, lifestyle, mood, or "what does my chart
  say about my health" are NOT medical — they are astrology questions about
  the user's profile and should be classified as "safe".
- "legal": the user is asking whether to take legal action, sign a contract,
  sue someone, or evaluate legal risk. Questions about justice in general,
  fate, or karmic patterns are NOT legal — classify as "safe".
- "safe": anything else, including all normal astrology, esoteric, life-path,
  relationship, career, money, transit, and personality questions.

Output STRICT JSON only, no markdown, no commentary, exactly one of:
  {"category": "medical"}
  {"category": "legal"}
  {"category": "safe"}

User question follows.
```

- [ ] **Step 2: Write the failing test**

`tests/test_moderation_advice_tier2.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.llm.base import LLMResult
from quantuum.moderation.classifier import _llm_advice_classifier
from quantuum.moderation.policy import Category, Safe, Tier2Hit


def _fake_llm(text: str):
    c = MagicMock()
    c.complete = AsyncMock(
        return_value=LLMResult(text=text, tokens_in=1, tokens_out=1, model="m")
    )
    return c


@pytest.mark.asyncio
async def test_tier2_safe_returns_safe():
    llm = _fake_llm('{"category": "safe"}')
    verdict = await _llm_advice_classifier(
        "what does my chart say about love?", "ru", llm, model="m"
    )
    assert isinstance(verdict, Safe)


@pytest.mark.asyncio
async def test_tier2_medical_returns_tier2hit():
    llm = _fake_llm('{"category": "medical"}')
    verdict = await _llm_advice_classifier(
        "should I stop taking my SSRIs?", "ru", llm, model="m"
    )
    assert isinstance(verdict, Tier2Hit) and verdict.category is Category.MEDICAL_ADVICE


@pytest.mark.asyncio
async def test_tier2_legal_returns_tier2hit():
    llm = _fake_llm('{"category": "legal"}')
    verdict = await _llm_advice_classifier(
        "should I sue my landlord?", "ru", llm, model="m"
    )
    assert isinstance(verdict, Tier2Hit) and verdict.category is Category.LEGAL_ADVICE


@pytest.mark.asyncio
async def test_tier2_invalid_json_returns_safe():
    """Garbled mini-LLM output fails open."""
    llm = _fake_llm("definitely not json")
    verdict = await _llm_advice_classifier("text", "ru", llm, model="m")
    assert isinstance(verdict, Safe)


@pytest.mark.asyncio
async def test_tier2_unknown_category_returns_safe():
    llm = _fake_llm('{"category": "weather"}')
    verdict = await _llm_advice_classifier("text", "ru", llm, model="m")
    assert isinstance(verdict, Safe)


@pytest.mark.asyncio
async def test_tier2_passes_lang_into_user_payload():
    llm = _fake_llm('{"category": "safe"}')
    await _llm_advice_classifier("какая моя судьба?", "ru", llm, model="m")
    call = llm.complete.await_args
    assert "User question (ru):" in call.kwargs["user"]
    assert "какая моя судьба?" in call.kwargs["user"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_advice_tier2.py -v`
Expected: FAIL with `ImportError: cannot import name '_llm_advice_classifier' from 'quantuum.moderation.classifier'`

- [ ] **Step 4: Add `_llm_advice_classifier`**

Append to `src/quantuum/moderation/classifier.py`:

```python
import json as _json
from pathlib import Path as _Path

from quantuum.moderation.policy import Tier2Hit

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_advice_tier2.py -v`
Expected: PASS, 6/6.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/moderation/prompts/advice_classifier.txt src/quantuum/moderation/classifier.py tests/test_moderation_advice_tier2.py
git commit -m "feat(moderation): Tier2 mini-LLM advice classifier (medical/legal) with JSON parsing"
```

---

## Task 5: `moderate()` coordinator

**Files:**
- Modify: `src/quantuum/moderation/classifier.py`
- Modify: `src/quantuum/moderation/__init__.py` (re-export `moderate`)
- Test: `tests/test_moderation_coordinator.py`

- [ ] **Step 1: Write the failing test**

`tests/test_moderation_coordinator.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.llm.base import LLMResult
from quantuum.moderation import moderate
from quantuum.moderation.policy import Category, Safe, Tier1Hit, Tier2Hit


def _openai_resp(*, self_harm=False, violence=False, sexual_minors=False, hate=False):
    cats = MagicMock(
        self_harm=self_harm,
        self_harm_intent=self_harm,
        self_harm_instructions=self_harm,
        violence=violence,
        violence_graphic=violence,
        sexual_minors=sexual_minors,
        hate=hate,
        hate_threatening=hate,
    )
    r = MagicMock()
    r.results = [MagicMock(categories=cats)]
    return r


def _mk_openai(*, hit=False, raises=None):
    client = MagicMock()
    if raises is not None:
        client.moderations.create = AsyncMock(side_effect=raises)
    else:
        client.moderations.create = AsyncMock(
            return_value=_openai_resp(self_harm=hit)
        )
    return client


def _mk_llm(*, text='{"category": "safe"}', raises=None):
    client = MagicMock()
    if raises is not None:
        client.complete = AsyncMock(side_effect=raises)
    else:
        client.complete = AsyncMock(
            return_value=LLMResult(text=text, tokens_in=1, tokens_out=1, model="m")
        )
    return client


def _settings(**overrides):
    base = dict(
        moderation_enabled=True,
        moderation_fail_open=True,
        moderation_openai_model="omni-moderation-latest",
        moderation_advice_model=None,
        moderation_advice_max_tokens=32,
        moderation_advice_temperature=0.0,
        llm_model="gpt-4o",
    )
    base.update(overrides)
    return MagicMock(**base)


@pytest.mark.asyncio
async def test_clean_input_returns_safe():
    v = await moderate(
        "what's my rising sign?",
        "ru",
        openai_client=_mk_openai(hit=False),
        llm_client=_mk_llm(),
        settings=_settings(),
    )
    assert isinstance(v, Safe)


@pytest.mark.asyncio
async def test_tier1_wins_over_tier2():
    v = await moderate(
        "i want to hurt myself and need legal advice",
        "ru",
        openai_client=_mk_openai(hit=True),
        llm_client=_mk_llm(text='{"category": "legal"}'),
        settings=_settings(),
    )
    assert isinstance(v, Tier1Hit) and v.category is Category.SELF_HARM


@pytest.mark.asyncio
async def test_tier2_used_when_tier1_safe():
    v = await moderate(
        "should I sue my landlord?",
        "ru",
        openai_client=_mk_openai(hit=False),
        llm_client=_mk_llm(text='{"category": "legal"}'),
        settings=_settings(),
    )
    assert isinstance(v, Tier2Hit) and v.category is Category.LEGAL_ADVICE


@pytest.mark.asyncio
async def test_kill_switch_skips_all_calls():
    openai = _mk_openai(hit=True)
    llm = _mk_llm(text='{"category": "medical"}')
    v = await moderate(
        "i want to hurt myself",
        "ru",
        openai_client=openai,
        llm_client=llm,
        settings=_settings(moderation_enabled=False),
    )
    assert isinstance(v, Safe)
    openai.moderations.create.assert_not_called()
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_tier1_exception_fails_open_when_enabled():
    v = await moderate(
        "what's my chart?",
        "ru",
        openai_client=_mk_openai(raises=RuntimeError("upstream 500")),
        llm_client=_mk_llm(),
        settings=_settings(moderation_fail_open=True),
    )
    assert isinstance(v, Safe)


@pytest.mark.asyncio
async def test_tier2_exception_fails_open_when_enabled():
    v = await moderate(
        "what's my chart?",
        "ru",
        openai_client=_mk_openai(hit=False),
        llm_client=_mk_llm(raises=RuntimeError("upstream 500")),
        settings=_settings(moderation_fail_open=True),
    )
    assert isinstance(v, Safe)


@pytest.mark.asyncio
async def test_tier1_exception_raises_when_fail_open_disabled():
    with pytest.raises(RuntimeError):
        await moderate(
            "text",
            "ru",
            openai_client=_mk_openai(raises=RuntimeError("upstream 500")),
            llm_client=_mk_llm(),
            settings=_settings(moderation_fail_open=False),
        )


@pytest.mark.asyncio
async def test_advice_model_override_used_when_set():
    llm = _mk_llm()
    await moderate(
        "text",
        "ru",
        openai_client=_mk_openai(),
        llm_client=llm,
        settings=_settings(moderation_advice_model="gpt-4o-mini"),
    )
    assert llm.complete.await_args.kwargs["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_advice_model_falls_back_to_llm_model():
    llm = _mk_llm()
    await moderate(
        "text",
        "ru",
        openai_client=_mk_openai(),
        llm_client=llm,
        settings=_settings(moderation_advice_model=None, llm_model="gpt-4o"),
    )
    assert llm.complete.await_args.kwargs["model"] == "gpt-4o"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_coordinator.py -v`
Expected: FAIL with `ImportError: cannot import name 'moderate' from 'quantuum.moderation'`

- [ ] **Step 3: Add `moderate()` to `classifier.py` and export it**

Append to `src/quantuum/moderation/classifier.py`:

```python
import asyncio


from quantuum.logging_setup import get_logger as _get_logger

_log = _get_logger("moderation")


async def moderate(
    text: str,
    lang: str,
    *,
    openai_client,
    llm_client,
    settings,
) -> "Safe | Tier1Hit | Tier2Hit":
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
```

Update `src/quantuum/moderation/__init__.py` to also re-export `moderate`:

```python
from quantuum.moderation.classifier import moderate
from quantuum.moderation.policy import (
    Action,
    Category,
    ModerationVerdict,
    POLICY,
    Safe,
    Tier,
    Tier1Hit,
    Tier2Hit,
)

__all__ = [
    "Action",
    "Category",
    "ModerationVerdict",
    "POLICY",
    "Safe",
    "Tier",
    "Tier1Hit",
    "Tier2Hit",
    "moderate",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_coordinator.py -v`
Expected: PASS, 9/9.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/moderation/classifier.py src/quantuum/moderation/__init__.py tests/test_moderation_coordinator.py
git commit -m "feat(moderation): moderate() coordinator with parallel Tier1+Tier2, kill switch, fail-open"
```

---

## Task 6: `ModerationEvent` model + Alembic migration

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/d0e1f2a3b4c5_moderation_events.py`
- Test: `tests/test_moderation_events_db.py`

- [ ] **Step 1: Write the failing test**

`tests/test_moderation_events_db.py`:

```python
import pytest
from sqlalchemy import select

from quantuum.db.models import ModerationEvent


@pytest.mark.asyncio
async def test_moderation_event_row_persists(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="42"
    )
    ev = ModerationEvent(
        account_id=acc.id,
        tenant_id=default_tenant.id,
        lang="ru",
        category="self_harm",
        action="soft_redirect",
        source="openai",
        text_sha256=b"\x00" * 32,
        text_preview="hello world",
    )
    session.add(ev)
    await session.commit()

    rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].category == "self_harm"
    assert rows[0].action == "soft_redirect"
    assert rows[0].source == "openai"
    assert rows[0].text_sha256 == b"\x00" * 32
    assert rows[0].text_preview == "hello world"
    assert rows[0].created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_events_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'ModerationEvent' from 'quantuum.db.models'`

- [ ] **Step 3: Add the model**

In `src/quantuum/db/models.py`, after the `Reading` class definition (line ~190), add:

```python
class ModerationEvent(SQLModel, table=True):
    __tablename__ = "moderation_events"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int | None = Field(default=None, foreign_key="accounts.id", index=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    lang: str | None = Field(default=None, max_length=8)
    category: str  # Category enum value
    action: str  # Action enum value
    source: str  # "openai" | "mini_llm"
    text_sha256: bytes = Field(
        sa_column=Column(sa.LargeBinary(length=32), nullable=False),
    )
    text_preview: str = Field(max_length=80)
    created_at: datetime = _dt_field(default_factory=utcnow, index=True)
```

If `sa` is not yet imported as a top-level alias in this file, replace `sa.LargeBinary` with the already-imported `LargeBinary` from sqlalchemy (add `LargeBinary` to the existing `from sqlalchemy import ...` line at the top of the file).

- [ ] **Step 4: Create the Alembic migration**

`alembic/versions/d0e1f2a3b4c5_moderation_events.py`:

```python
"""moderation_events table

Revision ID: d0e1f2a3b4c5
Revises: b8c9d0e1f2a3
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=True),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("text_preview", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_moderation_events_account_id", "moderation_events", ["account_id"])
    op.create_index("ix_moderation_events_tenant_id", "moderation_events", ["tenant_id"])
    op.create_index("ix_moderation_events_created_at", "moderation_events", ["created_at"])
    op.create_index(
        "ix_moderation_events_category_created",
        "moderation_events",
        ["category", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_events_category_created", table_name="moderation_events")
    op.drop_index("ix_moderation_events_created_at", table_name="moderation_events")
    op.drop_index("ix_moderation_events_tenant_id", table_name="moderation_events")
    op.drop_index("ix_moderation_events_account_id", table_name="moderation_events")
    op.drop_table("moderation_events")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_events_db.py -v`
Expected: PASS (test uses `SQLModel.metadata.create_all` from conftest, so the new model is picked up automatically; the migration file is for the app DB and not exercised by the test).

- [ ] **Step 6: Apply the migration to the app DB**

Run: `docker compose run --rm app uv run alembic upgrade head`
Expected: applies `d0e1f2a3b4c5` revision.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/d0e1f2a3b4c5_moderation_events.py tests/test_moderation_events_db.py
git commit -m "feat(moderation): moderation_events table (sha256 + 80-char preview, no cleartext)"
```

---

## Task 7: `record_moderation_event` domain function

**Files:**
- Create: `src/quantuum/domain/moderation.py`
- Test: extend `tests/test_moderation_events_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_moderation_events_db.py`:

```python
@pytest.mark.asyncio
async def test_record_moderation_event_computes_hash_and_preview(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.moderation import record_moderation_event
    from quantuum.moderation.policy import Action, Category

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="43"
    )
    raw = "x" * 200  # longer than the 80-char preview cap
    ev = await record_moderation_event(
        session,
        account_id=acc.id,
        tenant_id=default_tenant.id,
        lang="ru",
        category=Category.SELF_HARM,
        action=Action.SOFT_REDIRECT,
        source="openai",
        raw_text=raw,
    )
    await session.commit()
    assert ev.id is not None
    assert ev.category == "self_harm"
    assert ev.action == "soft_redirect"
    assert ev.source == "openai"
    assert len(ev.text_preview) == 80
    assert ev.text_preview == "x" * 80
    assert len(ev.text_sha256) == 32

    import hashlib
    assert ev.text_sha256 == hashlib.sha256(raw.encode("utf-8")).digest()


@pytest.mark.asyncio
async def test_record_moderation_event_short_text_not_padded(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.moderation import record_moderation_event
    from quantuum.moderation.policy import Action, Category

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="44"
    )
    ev = await record_moderation_event(
        session,
        account_id=acc.id,
        tenant_id=default_tenant.id,
        lang="ru",
        category=Category.MEDICAL_ADVICE,
        action=Action.SOFT_REDIRECT,
        source="mini_llm",
        raw_text="short text",
    )
    await session.commit()
    assert ev.text_preview == "short text"  # no padding
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_events_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.domain.moderation'`

- [ ] **Step 3: Implement the writer**

`src/quantuum/domain/moderation.py`:

```python
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.db.models import ModerationEvent
from quantuum.moderation.policy import Action, Category

_PREVIEW_MAX = 80


async def record_moderation_event(
    session: AsyncSession,
    *,
    account_id: int | None,
    tenant_id: int,
    lang: str | None,
    category: Category,
    action: Action,
    source: str,
    raw_text: str,
) -> ModerationEvent:
    """Persist a moderation event with sha256(raw) and an 80-char preview.

    Raw text is NOT stored. Caller controls commit boundary.
    """
    digest = hashlib.sha256(raw_text.encode("utf-8")).digest()
    preview = raw_text[:_PREVIEW_MAX]
    ev = ModerationEvent(
        account_id=account_id,
        tenant_id=tenant_id,
        lang=lang,
        category=category.value,
        action=action.value,
        source=source,
        text_sha256=digest,
        text_preview=preview,
    )
    session.add(ev)
    await session.flush()
    return ev
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_events_db.py -v`
Expected: PASS, all 3.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/moderation.py tests/test_moderation_events_db.py
git commit -m "feat(moderation): record_moderation_event domain writer (sha256 + preview cap)"
```

---

## Task 8: i18n strings (10 languages)

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Modify: `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`
- Test: `tests/test_moderation_i18n.py`

- [ ] **Step 1: Write the failing test**

`tests/test_moderation_i18n.py`:

```python
import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

MODERATION_KEYS = [
    "moderation.self_harm",
    "moderation.violence",
    "moderation.hate",
    "moderation.medical",
    "moderation.legal",
    "moderation.blocked_generic",
    "moderation.helpline_url",
]


@pytest.mark.parametrize("key", MODERATION_KEYS)
def test_base_strings_has_key_in_ru_and_en(key):
    assert key in BASE_STRINGS, f"missing {key} in BASE_STRINGS"
    entry = BASE_STRINGS[key]
    assert "ru" in entry and "en" in entry
    assert entry["ru"] and entry["en"]


@pytest.mark.parametrize(
    "lang_mod, lang_code",
    [(de, "de"), (es, "es"), (fr, "fr"), (hi, "hi"), (it, "it"), (pt, "pt"), (tr, "tr"), (zh, "zh")],
)
@pytest.mark.parametrize("key", MODERATION_KEYS)
def test_translation_modules_have_all_keys(lang_mod, lang_code, key):
    assert key in lang_mod.TRANSLATIONS, f"missing {key} in {lang_code}"
    assert lang_mod.TRANSLATIONS[key], f"empty {key} in {lang_code}"


def test_self_harm_message_contains_helpline_placeholder():
    assert "{helpline_url}" in BASE_STRINGS["moderation.self_harm"]["ru"]
    assert "{helpline_url}" in BASE_STRINGS["moderation.self_harm"]["en"]


def test_helpline_url_identical_across_locales():
    url = BASE_STRINGS["moderation.helpline_url"]["en"]
    assert url.startswith("https://")
    for mod in (de, es, fr, hi, it, pt, tr, zh):
        assert mod.TRANSLATIONS["moderation.helpline_url"] == url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_moderation_i18n.py -v`
Expected: FAIL — keys missing.

- [ ] **Step 3: Add keys to `BASE_STRINGS`**

In `src/quantuum/i18n/seed_strings.py`, append at the bottom of the `BASE_STRINGS` dict (just before its closing brace):

```python
    # -------------------------------------------------------------------------
    # Content moderation
    # -------------------------------------------------------------------------
    "moderation.self_harm": {
        "ru": (
            "Если ты сейчас в трудной точке — обратись за поддержкой: {helpline_url}. "
            "Я не заменяю специалиста, но я рядом."
        ),
        "en": (
            "If you're in a hard place right now, please reach out for support: "
            "{helpline_url}. I'm not a substitute for a professional, but I'm here."
        ),
    },
    "moderation.violence": {
        "ru": "Этот вопрос за пределами того, чем я могу помочь.",
        "en": "This question is outside what I can help with.",
    },
    "moderation.hate": {
        "ru": "Я тут не для этого.",
        "en": "I'm not here for that.",
    },
    "moderation.medical": {
        "ru": "Это вопрос к врачу, не к астрологу. Клинических рекомендаций я не даю.",
        "en": "This is a question for a doctor, not an astrologer. I don't give clinical guidance.",
    },
    "moderation.legal": {
        "ru": "Это к юристу. Я могу говорить про энергии и циклы, но не про правовые риски.",
        "en": "That's for a lawyer. I can speak to energies and cycles, not legal risk.",
    },
    "moderation.blocked_generic": {
        "ru": "Этот запрос невозможен.",
        "en": "This request can't be processed.",
    },
    "moderation.helpline_url": {
        "ru": "https://findahelpline.com/topics/suicidal-thoughts",
        "en": "https://findahelpline.com/topics/suicidal-thoughts",
    },
```

- [ ] **Step 4: Add keys to each translation file**

For each of `de.py, es.py, fr.py, hi.py, it.py, pt.py, tr.py, zh.py` in `src/quantuum/i18n/translations/`, append inside the `TRANSLATIONS` dict (just before its closing brace) the entries below. **Keep `moderation.helpline_url` identical to the English URL.**

`de.py`:
```python
    "moderation.self_harm": "Wenn du gerade an einem schweren Punkt bist, hol dir bitte Unterstützung: {helpline_url}. Ich ersetze keine Fachperson, aber ich bin da.",
    "moderation.violence": "Diese Frage liegt außerhalb dessen, womit ich helfen kann.",
    "moderation.hate": "Dafür bin ich nicht da.",
    "moderation.medical": "Das ist eine Frage für Ärztinnen oder Ärzte, nicht für Astrologie. Klinische Ratschläge gebe ich nicht.",
    "moderation.legal": "Das ist eine Frage für einen Anwalt. Ich rede über Energien und Zyklen, nicht über rechtliche Risiken.",
    "moderation.blocked_generic": "Diese Anfrage kann nicht bearbeitet werden.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`es.py`:
```python
    "moderation.self_harm": "Si ahora estás en un momento difícil, busca apoyo: {helpline_url}. No sustituyo a un profesional, pero estoy aquí.",
    "moderation.violence": "Esta pregunta queda fuera de lo que puedo ayudarte.",
    "moderation.hate": "No estoy aquí para eso.",
    "moderation.medical": "Eso es para un médico, no para astrología. No doy recomendaciones clínicas.",
    "moderation.legal": "Eso es para un abogado. Puedo hablar de energías y ciclos, no de riesgos legales.",
    "moderation.blocked_generic": "Esta solicitud no se puede procesar.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`fr.py`:
```python
    "moderation.self_harm": "Si tu traverses un moment difficile, demande du soutien : {helpline_url}. Je ne remplace pas un professionnel, mais je suis là.",
    "moderation.violence": "Cette question dépasse ce que je peux faire.",
    "moderation.hate": "Je ne suis pas là pour ça.",
    "moderation.medical": "C'est une question pour un médecin, pas pour l'astrologie. Je ne donne pas de conseils cliniques.",
    "moderation.legal": "C'est pour un avocat. Je parle d'énergies et de cycles, pas de risques juridiques.",
    "moderation.blocked_generic": "Cette demande ne peut pas être traitée.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`hi.py`:
```python
    "moderation.self_harm": "अगर आप अभी कठिन समय में हैं, तो कृपया सहायता लें: {helpline_url}. मैं किसी विशेषज्ञ की जगह नहीं ले सकता, पर मैं यहाँ हूँ.",
    "moderation.violence": "यह सवाल मेरी मदद की सीमा के बाहर है.",
    "moderation.hate": "मैं इसके लिए नहीं हूँ.",
    "moderation.medical": "यह डॉक्टर के लिए सवाल है, ज्योतिष के लिए नहीं. मैं चिकित्सकीय सलाह नहीं देता.",
    "moderation.legal": "यह वकील के लिए है. मैं ऊर्जा और चक्रों की बात करता हूँ, कानूनी जोखिमों की नहीं.",
    "moderation.blocked_generic": "यह अनुरोध संसाधित नहीं किया जा सकता.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`it.py`:
```python
    "moderation.self_harm": "Se ora stai attraversando un momento difficile, chiedi supporto: {helpline_url}. Non sostituisco un professionista, ma ci sono.",
    "moderation.violence": "Questa domanda è oltre ciò con cui posso aiutarti.",
    "moderation.hate": "Non sono qui per questo.",
    "moderation.medical": "È una domanda per un medico, non per l'astrologia. Non do consigli clinici.",
    "moderation.legal": "Quello è per un avvocato. Parlo di energie e cicli, non di rischi legali.",
    "moderation.blocked_generic": "Questa richiesta non può essere elaborata.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`pt.py`:
```python
    "moderation.self_harm": "Se você está num momento difícil, procure apoio: {helpline_url}. Não substituo um profissional, mas estou aqui.",
    "moderation.violence": "Essa pergunta está fora do que posso ajudar.",
    "moderation.hate": "Não estou aqui para isso.",
    "moderation.medical": "Isso é com um médico, não com astrologia. Não dou orientação clínica.",
    "moderation.legal": "Isso é com um advogado. Falo de energias e ciclos, não de riscos jurídicos.",
    "moderation.blocked_generic": "Esta solicitação não pode ser processada.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`tr.py`:
```python
    "moderation.self_harm": "Şu an zor bir noktadaysan, lütfen destek al: {helpline_url}. Uzmanın yerine geçmem ama buradayım.",
    "moderation.violence": "Bu soru, yardım edebileceklerimin dışında.",
    "moderation.hate": "Bunun için burada değilim.",
    "moderation.medical": "Bu doktorluk konusu, astroloji değil. Klinik tavsiye vermem.",
    "moderation.legal": "Bu avukatlık konusu. Enerjilerden ve döngülerden bahsederim, hukuki risklerden değil.",
    "moderation.blocked_generic": "Bu istek işleme alınamıyor.",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

`zh.py`:
```python
    "moderation.self_harm": "如果你正处在艰难时刻，请寻求支持：{helpline_url}。我不能替代专业人士，但我会在这里。",
    "moderation.violence": "这个问题超出了我能帮助的范围。",
    "moderation.hate": "我不是为这个而在这里的。",
    "moderation.medical": "这是医生的问题，不是占星的问题。我不提供临床建议。",
    "moderation.legal": "这是律师的问题。我谈能量与周期，不谈法律风险。",
    "moderation.blocked_generic": "无法处理此请求。",
    "moderation.helpline_url": "https://findahelpline.com/topics/suicidal-thoughts",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_moderation_i18n.py -v`
Expected: PASS — 7 keys × 10 languages.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/ tests/test_moderation_i18n.py
git commit -m "feat(moderation): i18n strings for 6 categories + helpline URL × 10 languages"
```

---

## Task 9: Wire `moderate()` into the QA handler

**Files:**
- Modify: `src/quantuum/bot/handlers/qa.py`
- Test: `tests/test_qa_moderation_e2e.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_qa_moderation_e2e.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.qa import _submit
from quantuum.db.models import (
    AccountBalance,
    ModerationEvent,
    QA,
    Request,
)
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.moderation.policy import Category, Safe, Tier1Hit, Tier2Hit
from tests.conftest import build_translator


async def _setup_account(session, tenant_id):
    from datetime import date, time
    from decimal import Decimal

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="m1")
    await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    await session.commit()
    return acc


def _make_message():
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.chat.id = 12345
    return msg


async def test_clean_question_passes_through(session, default_tenant):
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()

    with patch("quantuum.bot.handlers.qa.moderate", new=AsyncMock(return_value=Safe())):
        await _submit(msg, "what does my chart say about love?", acc, i18n)

    # qa row created, request created, quota deducted, no moderation_event
    qa_rows = (await session.execute(select(QA))).scalars().all()
    req_rows = (await session.execute(select(Request))).scalars().all()
    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(qa_rows) == 1
    assert len(req_rows) == 1
    assert len(me_rows) == 0


async def test_self_harm_blocks_creates_event_no_charge(session, default_tenant):
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    bal_before = await session.get(AccountBalance, acc.id)
    starting_credits = bal_before.package_credits
    msg = _make_message()

    with patch(
        "quantuum.bot.handlers.qa.moderate",
        new=AsyncMock(return_value=Tier1Hit(category=Category.SELF_HARM)),
    ):
        await _submit(msg, "i want to hurt myself", acc, i18n)

    qa_rows = (await session.execute(select(QA))).scalars().all()
    req_rows = (await session.execute(select(Request))).scalars().all()
    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert qa_rows == []
    assert req_rows == []
    assert len(me_rows) == 1
    assert me_rows[0].category == "self_harm"
    assert me_rows[0].action == "soft_redirect"
    assert me_rows[0].source == "openai"

    bal_after = await session.get(AccountBalance, acc.id)
    await session.refresh(bal_after)
    assert bal_after.package_credits == starting_credits

    msg.answer.assert_awaited_once()
    sent_text = msg.answer.await_args.args[0]
    assert "findahelpline.com" in sent_text


async def test_medical_advice_blocks_creates_event_no_charge(session, default_tenant):
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    bal_before = await session.get(AccountBalance, acc.id)
    starting_credits = bal_before.package_credits
    msg = _make_message()

    with patch(
        "quantuum.bot.handlers.qa.moderate",
        new=AsyncMock(return_value=Tier2Hit(category=Category.MEDICAL_ADVICE)),
    ):
        await _submit(msg, "should I stop taking my SSRIs?", acc, i18n)

    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(me_rows) == 1
    assert me_rows[0].category == "medical_advice"
    assert me_rows[0].source == "mini_llm"
    bal_after = await session.get(AccountBalance, acc.id)
    await session.refresh(bal_after)
    assert bal_after.package_credits == starting_credits
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_qa_moderation_e2e.py -v`
Expected: FAIL — `moderate` not imported in `qa.py`; first test will run the LLM-pipeline branch (existing code) — failures may appear differently. Capture failures and proceed.

- [ ] **Step 3: Wire moderation into the handler**

Modify `src/quantuum/bot/handlers/qa.py` `_submit()` function. Replace its body with:

```python
async def _submit(message: Message, raw: str, account: Account, i18n: Translator) -> None:
    q = (raw or "").strip()
    if not q:
        await message.answer(await i18n("qa.empty"))
        return
    if len(q) > MAX_QUESTION_LEN:
        await message.answer(await i18n("qa.too_long"))
        return

    # ─── Moderation pre-check (before any quota charge) ───
    from openai import AsyncOpenAI

    from quantuum.domain.moderation import record_moderation_event
    from quantuum.llm.registry import get_llm_client
    from quantuum.logging_setup import get_logger as _ml_get_logger
    from quantuum.moderation import POLICY, Safe, moderate
    from quantuum.moderation.policy import Action, Category, Tier1Hit, Tier2Hit
    from quantuum.settings import get_settings

    _moderation_log = _ml_get_logger("moderation.handler")

    settings = get_settings()
    if settings.moderation_enabled and settings.llm_api_key:
        openai_client = AsyncOpenAI(api_key=settings.llm_api_key)
        llm_client = get_llm_client(settings)
        try:
            verdict = await moderate(
                q,
                i18n.lang,
                openai_client=openai_client,
                llm_client=llm_client,
                settings=settings,
            )
        except Exception:
            verdict = Safe()  # last-resort fail-open guard

        if not isinstance(verdict, Safe):
            entry = POLICY[verdict.category]
            source = "openai" if isinstance(verdict, Tier1Hit) else "mini_llm"
            text_kwargs = {}
            if entry["uses_helpline"]:
                helpline = await i18n("moderation.helpline_url")
                text_kwargs["helpline_url"] = helpline
            response_text = await i18n(entry["i18n_key"], **text_kwargs)
            async with get_sessionmaker()() as session:
                await record_moderation_event(
                    session,
                    account_id=account.id,
                    tenant_id=account.tenant_id,
                    lang=i18n.lang,
                    category=verdict.category,
                    action=Action(entry["action"]),
                    source=source,
                    raw_text=q,
                )
                await session.commit()
            _moderation_log.info(
                "moderation.triggered",
                account_id=account.id,
                tenant_id=account.tenant_id,
                category=verdict.category.value,
                action=entry["action"].value,
                source=source,
                lang=i18n.lang,
            )
            await message.answer(response_text)
            return

    # ─── Existing flow: profile → quota → request → qa → enqueue ───
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message.answer(await i18n("qa.no_profile"))
            return
        try:
            charged = await consume_quota(session, account.id, "qa")
        except InsufficientFundsError:
            await message.answer(
                await i18n("qa.no_quota"), reply_markup=await _buy_offer_kb(i18n)
            )
            return
        request = await create_request(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            kind="qa",
            charged_against=charged,
        )
        qa = await create_qa(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            natal_profile_id=profile.id,
            question=q,
            lang=i18n.lang,
        )

    await enqueue_qa(qa.id, message.chat.id, request.id)
    await message.answer(await i18n("qa.thinking"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_qa_moderation_e2e.py -v`
Expected: PASS, 3/3.

- [ ] **Step 5: Run the broader QA test suite to confirm no regressions**

Run: `uv run pytest tests/test_qa_*.py tests/test_task_qa.py -v`
Expected: All existing QA tests pass (they don't patch `moderate`, so they go through the real moderation path. The handler skips moderation when `settings.llm_api_key` is empty — and test env doesn't set it. Verify this assumption holds; if any test breaks because it sets `llm_api_key`, mock `moderate` in that test or use `monkeypatch.setattr` on the settings field to disable moderation).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/qa.py tests/test_qa_moderation_e2e.py
git commit -m "feat(moderation): wire pre-LLM moderate() into QA handler (block before quota charge)"
```

---

## Task 10: Full suite gate

**Files:**
- None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass. Investigate any failures and patch in this branch before merge.

- [ ] **Step 2: Verify ruff is clean**

Run: `uv run ruff check src/ tests/`
Expected: No issues. If there are any, fix them.

- [ ] **Step 3: Final commit if any cleanups were needed**

```bash
git status
# If any uncommitted changes from ruff/test fixes, commit them with:
git add -A && git commit -m "chore(moderation): final lint and test fixes"
```

---

## Notes for the implementer

- **Read patterns first.** Skim `src/quantuum/llm/qa_answer.py`, `src/quantuum/llm/openai_client.py`, and `src/quantuum/bot/handlers/qa.py` before starting Task 3. The codebase has consistent shapes (LLMClient protocol, prompt-from-file pattern, settings via pydantic-settings) — follow them.
- **No emojis in code/comments.** Project convention.
- **Tests run against a real Postgres** (`172.30.0.2`) — see `tests/conftest.py`. `session` and `default_tenant` fixtures are already wired; just inject them.
- **Migration revision IDs.** Latest is `b8c9d0e1f2a3`. New one is `d0e1f2a3b4c5`. If a competing migration has been added since this plan was written, bump down_revision to the actual head.
- **Asynchronous tests** need `@pytest.mark.asyncio` (project uses session-scoped event loop, see `pyproject.toml` `asyncio_*_loop_scope` config).
- **`Translator` interpolation.** `await i18n("key", helpline_url=...)` substitutes `{helpline_url}` in the localized string. Confirm by reading `quantuum.i18n.Translator.__call__` before Task 9 if unsure.
- **Failure of Task 9 step 5** is the only place where an existing test might break — handle by either mocking `moderate` in the test or skipping moderation in tests via `monkeypatch.setenv("MODERATION_ENABLED", "false")`. Do not regress production behavior.
