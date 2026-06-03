"""Handler-level tests for the /transits flow. Mirrors tests/test_qa_bot.py."""
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.models import AccountBalance, Request, TransitReport
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


async def _seed_account(session, tenant_id, tg_user_id, *, profile=True, credits=0):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg_user_id)
    if profile:
        await upsert_natal_profile(
            session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
            birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
            latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
        )
    balance = await session.get(AccountBalance, acc.id)
    if balance is None:
        balance = AccountBalance(account_id=acc.id)
    balance.free_trial_used = True
    balance.package_credits = credits
    session.add(balance)
    await session.commit()
    return acc


async def test_transits_with_quota_consumes_and_enqueues(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import transits

    _patch_sessionmaker(monkeypatch, transits, session)
    spy = AsyncMock()
    monkeypatch.setattr(transits, "enqueue_transit", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "100", credits=2)

    msg = FakeMessage(text="/transits", chat_id=100)
    command = SimpleNamespace(args=None)
    await transits.on_transits(msg, command, acc, i18n)

    rows = (await session.execute(select(TransitReport))).scalars().all()
    assert len(rows) == 1
    assert rows[0].window_days == 90
    reqs = (await session.execute(select(Request).where(Request.kind == "transit"))).scalars().all()
    assert len(reqs) == 1 and reqs[0].charged_against == "package"

    balance = await session.get(AccountBalance, acc.id)
    assert balance.package_credits == 1
    spy.assert_awaited_once_with(rows[0].id, 100, reqs[0].id)
    assert msg.answer.await_args.args[0] == "Считаю транзиты… ⏳"


async def test_transits_with_window_arg(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import transits

    _patch_sessionmaker(monkeypatch, transits, session)
    monkeypatch.setattr(transits, "enqueue_transit", AsyncMock())
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "101", credits=2)

    msg = FakeMessage(text="/transits 30", chat_id=101)
    command = SimpleNamespace(args="30")
    await transits.on_transits(msg, command, acc, i18n)

    row = (await session.execute(select(TransitReport))).scalars().first()
    assert row.window_days == 30


async def test_transits_no_quota_offers_buy(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import transits

    _patch_sessionmaker(monkeypatch, transits, session)
    spy = AsyncMock()
    monkeypatch.setattr(transits, "enqueue_transit", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "102", credits=0)

    msg = FakeMessage(text="/transits", chat_id=102)
    command = SimpleNamespace(args=None)
    await transits.on_transits(msg, command, acc, i18n)

    assert msg.answer.await_args.args[0] == (
        "Закончились разборы. Купи пакет или подписку, чтобы посмотреть транзиты:"
    )
    kb = msg.answer.await_args.kwargs["reply_markup"]
    assert BuyCb.unpack(kb.inline_keyboard[0][0].callback_data).action == "open"
    spy.assert_not_awaited()
    assert (await session.execute(select(TransitReport))).scalars().first() is None


async def test_transits_no_profile(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import transits

    _patch_sessionmaker(monkeypatch, transits, session)
    spy = AsyncMock()
    monkeypatch.setattr(transits, "enqueue_transit", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "103", profile=False, credits=2)

    msg = FakeMessage(text="/transits", chat_id=103)
    command = SimpleNamespace(args=None)
    await transits.on_transits(msg, command, acc, i18n)

    assert "натальный профиль" in msg.answer.await_args.args[0]
    spy.assert_not_awaited()
    balance = await session.get(AccountBalance, acc.id)
    assert balance.package_credits == 2
    assert (await session.execute(select(TransitReport))).scalars().first() is None


async def test_transits_no_profile_shows_fill_button(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import transits
    from quantuum.bot.ui.callbacks import OnboardCb
    from quantuum.auth.identity import find_or_create_account_by_tg
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from tests.conftest import build_translator

    _patch_sessionmaker(monkeypatch, transits, session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="520"
    )
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    msg = SimpleNamespace(text="/transits", chat=SimpleNamespace(id=520), answer=AsyncMock())
    await transits.run_transits(msg, None, acc, i18n)

    kb = msg.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None, "no-profile response must include a keyboard"
    btns = [b for row in kb.inline_keyboard for b in row]
    assert any(OnboardCb.unpack(b.callback_data).action == "start" for b in btns)


async def test_transits_enqueue_failure_refunds_credit(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import transits

    _patch_sessionmaker(monkeypatch, transits, session)
    monkeypatch.setattr(
        transits, "enqueue_transit",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "199", credits=2)

    msg = FakeMessage(text="/transits", chat_id=199)
    command = SimpleNamespace(args=None)
    await transits.on_transits(msg, command, acc, i18n)

    expected = await i18n("errors.queue_failed")
    answers = [c.args[0] for c in msg.answer.await_args_list]
    assert expected in answers

    balance = await session.get(AccountBalance, acc.id)
    await session.refresh(balance)
    assert balance.package_credits == 2  # refunded back to starting value

    reqs = (await session.execute(select(Request).where(Request.kind == "transit"))).scalars().all()
    assert len(reqs) == 1
    await session.refresh(reqs[0])
    assert reqs[0].charged_against == "none"
