from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.bot.handlers.divination import (
    Divination,
    on_divination_choice,
    on_divination_question,
    on_divination_skip,
)
from quantuum.bot.ui.callbacks import ReadingCb
from quantuum.db.models import AccountBalance, NatalProfile, Reading


def _query(tg_id: int, kind: str = "tarot"):
    q = MagicMock()
    q.from_user = MagicMock(id=tg_id)
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    q.message.chat = MagicMock(id=tg_id)
    q.answer = AsyncMock()
    q.data = ReadingCb(action="generate", kind=kind).pack()
    return q


def _state(tg_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id),
    )


async def _seed_account_with_profile_and_credits(session, default_tenant, *, credits=10):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="42"
    )
    profile = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.commit()
    return acc


async def test_choice_enters_fsm(session, default_tenant):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    q = _query(tg_id=42, kind="tarot")
    state = _state(42)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_choice(
        q, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )
    assert await state.get_state() == Divination.awaiting_question.state
    data = await state.get_data()
    assert data["kind"] == "tarot"


async def test_choice_blocked_when_flag_off(session, default_tenant):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    from quantuum.domain.tenant_features import set_feature_enabled
    await set_feature_enabled(
        session, tenant_id=default_tenant.id, key="reading.tarot",
        enabled=False, by_account_id=acc.id,
    )
    await session.commit()

    q = _query(tg_id=42, kind="tarot")
    state = _state(42)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_choice(
        q, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )
    q.message.answer.assert_awaited()
    assert await state.get_state() is None


async def test_choice_blocked_when_no_profile(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="42"
    )
    await session.commit()
    q = _query(tg_id=42, kind="tarot")
    state = _state(42)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_choice(
        q, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )
    q.message.answer.assert_awaited()
    assert await state.get_state() is None


async def test_skip_path_creates_reading_with_null_question(session, default_tenant, monkeypatch):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    state = _state(42)
    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind="tarot")

    msg = MagicMock()
    msg.from_user = MagicMock(id=42)
    msg.chat = MagicMock(id=42)
    msg.answer = AsyncMock()

    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.enqueue_reading", AsyncMock()
    )

    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_skip(
        msg, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )

    from sqlalchemy import select
    readings = (await session.execute(
        select(Reading).where(Reading.account_id == acc.id)
    )).scalars().all()
    assert len(readings) == 1
    r = readings[0]
    assert r.kind == "tarot"
    assert r.draw_jsonb is not None
    assert r.draw_jsonb.get("question") is None
    assert len(r.draw_jsonb.get("cards", [])) == 3
    assert await state.get_state() is None


async def test_text_question_path_creates_reading_with_question(
    session, default_tenant, monkeypatch
):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    state = _state(42)
    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind="iching")

    msg = MagicMock()
    msg.text = "What should I do?"
    msg.from_user = MagicMock(id=42)
    msg.chat = MagicMock(id=42)
    msg.answer = AsyncMock()

    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.enqueue_reading", AsyncMock()
    )
    from quantuum.moderation import Safe
    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.moderate", AsyncMock(return_value=Safe()),
    )

    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_question(
        msg, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )

    from sqlalchemy import select
    r = (await session.execute(
        select(Reading).where(Reading.account_id == acc.id)
    )).scalars().one()
    assert r.kind == "iching"
    assert r.draw_jsonb.get("question") == "What should I do?"
    assert "primary_id" in r.draw_jsonb
    assert await state.get_state() is None


async def test_moderation_hit_aborts_without_quota_charge(
    session, default_tenant, monkeypatch
):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant, credits=10)
    state = _state(42)
    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind="tarot")

    msg = MagicMock()
    msg.text = "anything"
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()

    from quantuum.moderation import Tier1Hit
    from quantuum.moderation.policy import Category
    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.moderate",
        AsyncMock(return_value=Tier1Hit(category=Category.SELF_HARM)),
    )

    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_question(
        msg, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )

    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == 10
    from sqlalchemy import select
    rows = (await session.execute(
        select(Reading).where(Reading.account_id == acc.id)
    )).scalars().all()
    assert rows == []
    # Verify a moderation event row was written for the hit.
    from quantuum.db.models import ModerationEvent
    mod_rows = (await session.execute(
        select(ModerationEvent).where(ModerationEvent.account_id == acc.id)
    )).scalars().all()
    assert len(mod_rows) == 1
    assert mod_rows[0].category == "self_harm"
    assert await state.get_state() is None
