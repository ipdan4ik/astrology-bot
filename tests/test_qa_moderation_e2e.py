from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import (
    AccountBalance,
    ModerationEvent,
    QaAnswer,
    Request,
)
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.moderation.policy import Category, Safe, Tier1Hit, Tier2Hit
from tests.conftest import build_translator


def _stub_settings(monkeypatch, *, fail_open: bool = True):
    """Force moderation guard truthy regardless of .env presence.

    Also resolves the (possibly re-imported) handler module so that callers
    can use the same module instance that patches/monkeypatches target —
    `tests/test_menu_and_dispatcher.py` performs ``del sys.modules[...]`` on
    ``quantuum.bot.handlers.*`` which can leave stale references behind.
    """
    from quantuum.bot.handlers import qa as qa_handler

    stub = SimpleNamespace(
        moderation_enabled=True,
        moderation_fail_open=fail_open,
        llm_api_key="sk-test",
        llm_provider="openai",
    )
    monkeypatch.setattr(qa_handler, "get_settings", lambda: stub)
    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())
    return qa_handler


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


async def test_clean_question_passes_through(session, default_tenant, monkeypatch):
    qa_handler = _stub_settings(monkeypatch)
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()

    with patch("quantuum.bot.handlers.qa.moderate", new=AsyncMock(return_value=Safe())):
        await qa_handler._submit(msg, "what does my chart say about love?", acc, i18n)

    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
    req_rows = (await session.execute(select(Request))).scalars().all()
    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(qa_rows) == 1
    assert len(req_rows) == 1
    assert len(me_rows) == 0


async def test_self_harm_blocks_creates_event_no_charge(session, default_tenant, monkeypatch):
    qa_handler = _stub_settings(monkeypatch)
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    bal_before = await session.get(AccountBalance, acc.id)
    starting_credits = bal_before.package_credits
    msg = _make_message()

    with patch(
        "quantuum.bot.handlers.qa.moderate",
        new=AsyncMock(return_value=Tier1Hit(category=Category.SELF_HARM)),
    ):
        await qa_handler._submit(msg, "i want to hurt myself", acc, i18n)

    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
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


async def test_medical_advice_blocks_creates_event_no_charge(session, default_tenant, monkeypatch):
    qa_handler = _stub_settings(monkeypatch)
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    bal_before = await session.get(AccountBalance, acc.id)
    starting_credits = bal_before.package_credits
    msg = _make_message()

    with patch(
        "quantuum.bot.handlers.qa.moderate",
        new=AsyncMock(return_value=Tier2Hit(category=Category.MEDICAL_ADVICE)),
    ):
        await qa_handler._submit(msg, "should I stop taking my SSRIs?", acc, i18n)

    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(me_rows) == 1
    assert me_rows[0].category == "medical_advice"
    assert me_rows[0].action == "soft_redirect"
    assert me_rows[0].source == "mini_llm"
    bal_after = await session.get(AccountBalance, acc.id)
    await session.refresh(bal_after)
    assert bal_after.package_credits == starting_credits


async def test_moderate_exception_propagates_when_fail_open_disabled(
    session, default_tenant, monkeypatch
):
    """Kill-switch contract: with fail_open=False, an unexpected moderation
    exception must propagate rather than silently being treated as Safe."""
    import pytest

    qa_handler = _stub_settings(monkeypatch, fail_open=False)
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()

    with patch(
        "quantuum.bot.handlers.qa.moderate",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await qa_handler._submit(msg, "anything", acc, i18n)
