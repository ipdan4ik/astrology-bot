from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import BuyCb, DailyCb
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, DailySubscription
from quantuum.domain.natal_profiles import upsert_natal_profile

from .conftest import build_translator


def _patch_sessionmaker(monkeypatch, module, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(module, "get_sessionmaker", lambda: _Maker())


class FakeMessage:
    def __init__(self, text="", chat_id=1):
        self.text = text
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


class FakeCallback:
    def __init__(self, chat_id=1):
        self.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id), edit_text=AsyncMock())
        self.from_user = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


async def _seed(session, tenant_id, tg, *, subscriber=True, profile=True):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    if profile:
        await upsert_natal_profile(
            session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
            birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
            latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
        )
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    return acc


async def test_daily_command_subscriber_shows_status_off(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "100")

    msg = FakeMessage(text="/daily", chat_id=100)
    await daily.on_daily(msg, acc, i18n)
    assert msg.answer.await_args.args[0] == "Ежедневный гороскоп выключен."


async def test_daily_command_non_subscriber_upsell(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "101", subscriber=False)

    msg = FakeMessage(text="/daily", chat_id=101)
    await daily.on_daily(msg, acc, i18n)
    text = msg.answer.await_args.args[0]
    assert text == (
        "Ежедневный гороскоп доступен по подписке. "
        "Оформи подписку, чтобы получать его каждое утро:"
    )
    kb = msg.answer.await_args.kwargs["reply_markup"]
    assert BuyCb.unpack(kb.inline_keyboard[0][0].callback_data).action == "open"


async def test_daily_command_no_profile(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "102", profile=False)

    msg = FakeMessage(text="/daily", chat_id=102)
    await daily.on_daily(msg, acc, i18n)
    assert msg.answer.await_args.args[0] == "Сначала заполни натальный профиль (/profile)."


async def test_daily_toggle_enables(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "103")

    cb = FakeCallback(chat_id=103)
    await daily.on_daily_toggle(cb, acc, i18n)

    row = await session.get(DailySubscription, acc.id)
    assert row.enabled is True
    cb.message.edit_text.assert_awaited()
    assert cb.answer.await_args.args[0] == "Включил ежедневный гороскоп ✅"


async def test_daily_set_hour(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "104")

    cb = FakeCallback(chat_id=104)
    await daily.on_daily_set_hour(cb, DailyCb(action="set_hour", value=7), acc, i18n)

    row = await session.get(DailySubscription, acc.id)
    assert row.send_hour == 7
    assert (await session.execute(select(DailySubscription))).scalars().first().send_hour == 7


async def test_daily_set_hour_same_hour_swallows_not_modified(session, default_tenant, monkeypatch):
    from aiogram.exceptions import TelegramBadRequest

    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "106")

    cb = FakeCallback(chat_id=106)
    # Re-tapping the already-selected hour yields an identical view -> Telegram rejects the edit.
    cb.message.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(method=None, message="Bad Request: message is not modified")
    )
    # Must not raise, and the callback must still be answered (no stuck spinner).
    await daily.on_daily_set_hour(cb, DailyCb(action="set_hour", value=9), acc, i18n)
    cb.answer.assert_awaited_once()
