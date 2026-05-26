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
    assert isinstance(verdict, Tier2Hit)
    assert verdict.category is Category.MEDICAL_ADVICE


@pytest.mark.asyncio
async def test_tier2_legal_returns_tier2hit():
    llm = _fake_llm('{"category": "legal"}')
    verdict = await _llm_advice_classifier(
        "should I sue my landlord?", "ru", llm, model="m"
    )
    assert isinstance(verdict, Tier2Hit)
    assert verdict.category is Category.LEGAL_ADVICE


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
