from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import OwnerReferralsCb
from quantuum.db.models import AuditLog, Tenant
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    get_reward_credits,
)
from quantuum.i18n import Translator


def test_owner_referrals_cb_class_exists():
    cb = OwnerReferralsCb(action="open")
    assert cb.action == "open"


async def _setup(session: AsyncSession, *, seed_strings: bool = False) -> tuple[int, int]:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_user_id="9001"
        )
    ).id
    if seed_strings:
        from quantuum.db.bootstrap import ensure_base_strings
        await ensure_base_strings(session)
    await session.commit()
    return t.id, aid


async def test_referrals_open_renders_current_value(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_open

    tid, aid = await _setup(session, seed_strings=True)
    query = MagicMock()
    query.message = MagicMock()
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")
    cb = OwnerReferralsCb(action="open")

    await on_referrals_open(query, cb, account_id=aid, tenant_id=tid, i18n=i18n)

    args, kwargs = query.message.answer.call_args
    body = args[0] if args else kwargs.get("text", "")
    assert str(DEFAULT_REWARD_CREDITS) in body


async def test_referrals_edit_saves_value(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    message = MagicMock()
    message.text = "25"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")

    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    assert await get_reward_credits(session, tenant_id=tid) == 25


async def test_referrals_edit_validation_too_large(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    # Set FSM state so the validation-failure path retains state
    await state.set_state("OwnerReferrals:awaiting_value")
    message = MagicMock()
    message.text = "9999"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")

    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS
    assert (await state.get_state()) == "OwnerReferrals:awaiting_value"


async def test_referrals_edit_validation_not_a_number(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    await state.set_state("OwnerReferrals:awaiting_value")
    message = MagicMock()
    message.text = "abc"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")

    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS
    assert (await state.get_state()) == "OwnerReferrals:awaiting_value"


async def test_referrals_reset_clears_override(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )

    # set to 50
    msg_set = MagicMock()
    msg_set.text = "50"
    msg_set.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")
    await on_referrals_value(
        msg_set, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )
    assert await get_reward_credits(session, tenant_id=tid) == 50

    # reset
    msg_reset = MagicMock()
    msg_reset.text = "/reset"
    msg_reset.answer = AsyncMock()
    await on_referrals_value(
        msg_reset, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )
    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS


async def test_referrals_config_set_writes_audit(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    message = MagicMock()
    message.text = "33"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")
    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

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
