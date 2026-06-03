from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import (
    OwnerGifts,
    on_gifts_cancel,
    on_gifts_edit,
    on_gifts_open,
    on_gifts_reset,
    on_gifts_value,
)
from quantuum.bot.ui.callbacks import OwnerGiftsCb
from quantuum.db.models import TenantRole
from quantuum.domain.gifts import (
    DEFAULT_EXPIRY_DAYS,
    MAX_EXPIRY_DAYS,
    MIN_EXPIRY_DAYS,
    get_expiry_days,
)


async def _seed_owner(session, t_id, tg=42):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t_id, tg_user_id=str(tg)
    )
    session.add(TenantRole(tenant_id=t_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _query(tg_id: int):
    q = MagicMock()
    q.from_user = MagicMock(id=tg_id)
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    q.message.edit_text = AsyncMock()
    q.answer = AsyncMock()
    return q


def _make_state(tg_id: int) -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id))


async def test_open_shows_current_value(session, default_tenant):
    await _seed_owner(session, default_tenant.id)
    q = _query(42)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}:{kw}>")
    await on_gifts_open(
        q,
        callback_data=OwnerGiftsCb(action="open", tenant_id=default_tenant.id),
        i18n=i18n,
    )
    body = q.message.edit_text.await_args.args[0]
    assert "owner.gifts.title" in body
    assert f"value': {DEFAULT_EXPIRY_DAYS}" in body
    # Back-to-menu row present
    from quantuum.bot.ui.callbacks import OwnerManageCb
    markup = q.message.edit_text.await_args.kwargs.get("reply_markup")
    cbs = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    assert OwnerManageCb(action="menu", tenant_id=default_tenant.id).pack() in cbs


async def test_open_rejects_non_owner(session, default_tenant):
    q = _query(99)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")
    await on_gifts_open(
        q,
        callback_data=OwnerGiftsCb(action="open", tenant_id=default_tenant.id),
        i18n=i18n,
    )
    q.answer.assert_awaited()
    args, kwargs = q.answer.await_args
    assert kwargs.get("show_alert") is True


async def test_edit_sets_fsm_state(session, default_tenant):
    await _seed_owner(session, default_tenant.id)
    q = _query(42)
    state = _make_state(42)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")
    await on_gifts_edit(
        q,
        callback_data=OwnerGiftsCb(action="edit", tenant_id=default_tenant.id),
        state=state,
        i18n=i18n,
    )
    assert await state.get_state() == OwnerGifts.awaiting_value.state
    data = await state.get_data()
    assert data["tenant_id"] == default_tenant.id


async def test_value_happy_path_saves(session, default_tenant):
    await _seed_owner(session, default_tenant.id)
    msg = MagicMock()
    msg.text = "14"
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    state = _make_state(42)
    await state.update_data(tenant_id=default_tenant.id)
    await state.set_state(OwnerGifts.awaiting_value)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")

    await on_gifts_value(msg, state=state, i18n=i18n)

    from quantuum.db.session import get_sessionmaker
    async with get_sessionmaker()() as s2:
        assert await get_expiry_days(s2, tenant_id=default_tenant.id) == 14
    msg.answer.assert_awaited_with("<owner.gifts.saved>")
    assert await state.get_state() is None


@pytest.mark.parametrize("raw, key", [
    ("abc", "owner.gifts.not_a_number"),
    (str(MIN_EXPIRY_DAYS - 1), "owner.gifts.too_small"),
    (str(MAX_EXPIRY_DAYS + 1), "owner.gifts.too_large"),
])
async def test_value_validation_errors(session, default_tenant, raw, key):
    await _seed_owner(session, default_tenant.id)
    msg = MagicMock()
    msg.text = raw
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    state = _make_state(42)
    await state.update_data(tenant_id=default_tenant.id)
    await state.set_state(OwnerGifts.awaiting_value)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    await on_gifts_value(msg, state=state, i18n=i18n)
    msg.answer.assert_awaited()
    body = msg.answer.await_args.args[0]
    assert key in body
    assert await state.get_state() == OwnerGifts.awaiting_value.state


async def test_reset_restores_default(session, default_tenant):
    owner = await _seed_owner(session, default_tenant.id)
    from quantuum.domain.gifts import set_expiry_days
    from quantuum.db.session import get_sessionmaker

    async with get_sessionmaker()() as s2:
        await set_expiry_days(
            s2, tenant_id=default_tenant.id, days=90, by_account_id=owner.id
        )
        await s2.commit()

    q = _query(42)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")
    await on_gifts_reset(
        q,
        callback_data=OwnerGiftsCb(action="reset", tenant_id=default_tenant.id),
        i18n=i18n,
    )

    async with get_sessionmaker()() as s3:
        assert await get_expiry_days(s3, tenant_id=default_tenant.id) == DEFAULT_EXPIRY_DAYS
    q.message.answer.assert_awaited_with("<owner.gifts.reset>")


async def test_cancel_exits_fsm(session, default_tenant):
    msg = MagicMock()
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    state = _make_state(42)
    await state.set_state(OwnerGifts.awaiting_value)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    await on_gifts_cancel(msg, state=state, i18n=i18n)
    assert await state.get_state() is None
