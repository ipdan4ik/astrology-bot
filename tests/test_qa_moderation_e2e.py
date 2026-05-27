from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.qa import _submit
from quantuum.db.models import (
    AccountBalance,
    ModerationEvent,
    QaAnswer,
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


async def test_clean_question_passes_through(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()

    # Don't actually enqueue to Redis — stub it out.
    from quantuum.bot.handlers import qa as qa_handler

    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())

    with patch("quantuum.bot.handlers.qa.moderate", new=AsyncMock(return_value=Safe())):
        await _submit(msg, "what does my chart say about love?", acc, i18n)

    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
    req_rows = (await session.execute(select(Request))).scalars().all()
    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(qa_rows) == 1
    assert len(req_rows) == 1
    assert len(me_rows) == 0


async def test_self_harm_blocks_creates_event_no_charge(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    bal_before = await session.get(AccountBalance, acc.id)
    starting_credits = bal_before.package_credits
    msg = _make_message()

    from quantuum.bot.handlers import qa as qa_handler

    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())

    with patch(
        "quantuum.bot.handlers.qa.moderate",
        new=AsyncMock(return_value=Tier1Hit(category=Category.SELF_HARM)),
    ):
        await _submit(msg, "i want to hurt myself", acc, i18n)

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
    acc = await _setup_account(session, default_tenant.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    bal_before = await session.get(AccountBalance, acc.id)
    starting_credits = bal_before.package_credits
    msg = _make_message()

    from quantuum.bot.handlers import qa as qa_handler

    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())

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
