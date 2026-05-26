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
