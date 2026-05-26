from unittest.mock import AsyncMock, MagicMock

import pytest
from structlog.testing import capture_logs

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
    assert isinstance(v, Tier1Hit)
    assert v.category is Category.SELF_HARM


@pytest.mark.asyncio
async def test_tier2_used_when_tier1_safe():
    v = await moderate(
        "should I sue my landlord?",
        "ru",
        openai_client=_mk_openai(hit=False),
        llm_client=_mk_llm(text='{"category": "legal"}'),
        settings=_settings(),
    )
    assert isinstance(v, Tier2Hit)
    assert v.category is Category.LEGAL_ADVICE


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
    with capture_logs() as cap:
        v = await moderate(
            "what's my chart?",
            "ru",
            openai_client=_mk_openai(raises=RuntimeError("upstream 500")),
            llm_client=_mk_llm(),
            settings=_settings(moderation_fail_open=True),
        )
    assert isinstance(v, Safe)
    err_logs = [e for e in cap if e.get("event") == "moderation.api_error"]
    assert len(err_logs) == 1
    assert err_logs[0]["log_level"] == "warning"
    assert err_logs[0]["provider"] == "openai"
    assert "upstream 500" in err_logs[0]["error"]


@pytest.mark.asyncio
async def test_tier2_exception_fails_open_when_enabled():
    with capture_logs() as cap:
        v = await moderate(
            "what's my chart?",
            "ru",
            openai_client=_mk_openai(hit=False),
            llm_client=_mk_llm(raises=RuntimeError("upstream 500")),
            settings=_settings(moderation_fail_open=True),
        )
    assert isinstance(v, Safe)
    err_logs = [e for e in cap if e.get("event") == "moderation.api_error"]
    assert len(err_logs) == 1
    assert err_logs[0]["log_level"] == "warning"
    assert err_logs[0]["provider"] == "mini_llm"
    assert "upstream 500" in err_logs[0]["error"]


@pytest.mark.asyncio
async def test_tier1_exception_raises_when_fail_open_disabled():
    with capture_logs() as cap:
        with pytest.raises(RuntimeError):
            await moderate(
                "text",
                "ru",
                openai_client=_mk_openai(raises=RuntimeError("upstream 500")),
                llm_client=_mk_llm(),
                settings=_settings(moderation_fail_open=False),
            )
    err_logs = [e for e in cap if e.get("event") == "moderation.api_error"]
    assert len(err_logs) == 1
    assert err_logs[0]["provider"] == "openai"


@pytest.mark.asyncio
async def test_tier2_exception_raises_when_fail_open_disabled():
    with capture_logs() as cap:
        with pytest.raises(RuntimeError):
            await moderate(
                "text",
                "ru",
                openai_client=_mk_openai(hit=False),
                llm_client=_mk_llm(raises=RuntimeError("upstream 500")),
                settings=_settings(moderation_fail_open=False),
            )
    err_logs = [e for e in cap if e.get("event") == "moderation.api_error"]
    assert len(err_logs) == 1
    assert err_logs[0]["provider"] == "mini_llm"


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
