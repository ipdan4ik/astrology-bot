from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import OwnerReferralsCb
from quantuum.db.models import AuditLog, Tenant, TenantRole
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    get_reward_credits,
)
from tests.conftest import build_translator


def test_owner_referrals_cb_class_exists():
    cb = OwnerReferralsCb(action="open")
    assert cb.action == "open"


async def _make_owner(session, tenant_id, *, tg: str):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    session.add(TenantRole(tenant_id=tenant_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _make_query(tg_user_id: str):
    query = MagicMock()
    query.from_user = MagicMock()
    # Store as string so str() round-trip in handlers matches identity lookup.
    query.from_user.id = tg_user_id
    query.message = MagicMock()
    query.message.answer = AsyncMock()
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    return query


def _make_message(tg_user_id: str) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock()
    msg.from_user.id = int(tg_user_id)
    msg.answer = AsyncMock()
    return msg


def _make_fsm(tenant_id: int | None = None) -> FSMContext:
    storage = MemoryStorage()
    # Use a stable key; the exact ids don't matter for unit tests.
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=9001, user_id=9001),
    )
    return state


async def _setup(session: AsyncSession, *, tg: str = "9001") -> tuple[int, int]:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    acc = await _make_owner(session, t.id, tg=tg)
    return t.id, acc.id


async def test_referrals_open_renders_current_value(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_open

    tid, aid = await _setup(session, tg="9001")
    i18n = await build_translator(session, tid, lang="en")
    query = _make_query("9001")
    cb = OwnerReferralsCb(action="open", tenant_id=tid)

    await on_referrals_open(query, cb, i18n=i18n)

    query.message.edit_text.assert_awaited_once()
    args, kwargs = query.message.edit_text.call_args
    body = args[0] if args else kwargs.get("text", "")
    assert str(DEFAULT_REWARD_CREDITS) in body
    # Back-to-menu row present
    from quantuum.bot.ui.callbacks import OwnerManageCb
    markup = kwargs.get("reply_markup")
    cbs = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    assert OwnerManageCb(action="menu", tenant_id=tid).pack() in cbs


async def test_referrals_edit_saves_value(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session, tg="9002")
    i18n = await build_translator(session, tid, lang="en")
    state = _make_fsm()
    await state.update_data(tenant_id=tid)

    message = _make_message("9002")
    message.text = "25"

    await on_referrals_value(message, state=state, i18n=i18n)

    assert await get_reward_credits(session, tenant_id=tid) == 25


async def test_referrals_edit_validation_too_large(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session, tg="9003")
    i18n = await build_translator(session, tid, lang="en")
    state = _make_fsm()
    await state.update_data(tenant_id=tid)
    await state.set_state("OwnerReferrals:awaiting_value")

    message = _make_message("9003")
    message.text = "9999"

    await on_referrals_value(message, state=state, i18n=i18n)

    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS
    assert (await state.get_state()) == "OwnerReferrals:awaiting_value"


async def test_referrals_edit_validation_not_a_number(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session, tg="9004")
    i18n = await build_translator(session, tid, lang="en")
    state = _make_fsm()
    await state.update_data(tenant_id=tid)
    await state.set_state("OwnerReferrals:awaiting_value")

    message = _make_message("9004")
    message.text = "abc"

    await on_referrals_value(message, state=state, i18n=i18n)

    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS
    assert (await state.get_state()) == "OwnerReferrals:awaiting_value"


async def test_referrals_reset_clears_override(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session, tg="9005")
    i18n = await build_translator(session, tid, lang="en")
    state = _make_fsm()
    await state.update_data(tenant_id=tid)

    # set to 50
    msg_set = _make_message("9005")
    msg_set.text = "50"
    await on_referrals_value(msg_set, state=state, i18n=i18n)
    assert await get_reward_credits(session, tenant_id=tid) == 50

    # state was cleared after save; restore tenant_id for next call
    await state.update_data(tenant_id=tid)

    # reset
    msg_reset = _make_message("9005")
    msg_reset.text = "/reset"
    await on_referrals_value(msg_reset, state=state, i18n=i18n)
    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS


async def test_referrals_config_set_writes_audit(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session, tg="9006")
    i18n = await build_translator(session, tid, lang="en")
    state = _make_fsm()
    await state.update_data(tenant_id=tid)

    message = _make_message("9006")
    message.text = "33"
    await on_referrals_value(message, state=state, i18n=i18n)

    rows = (
        (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "referral.config_set")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) >= 1
