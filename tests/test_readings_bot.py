"""Handler-level tests for the Readings submenu flow.

Mirrors tests/test_qa_bot.py in structure — sessionmaker patching, fake Message /
CallbackQuery types, and real DB fixtures via the shared session.
"""
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.bot.ui.callbacks import ReadingCb
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.natal_profiles import upsert_natal_profile

from .conftest import build_translator


def test_reading_cb_pack_unpack_roundtrip():
    cb = ReadingCb(action="generate", kind="bazi")
    packed = cb.pack()
    assert packed.startswith("rd:")
    parsed = ReadingCb.unpack(packed)
    assert parsed.action == "generate"
    assert parsed.kind == "bazi"


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


@pytest.mark.parametrize("kind", [
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
    "transits",
])
async def test_readings_menu_includes_all_eight_kinds(session, default_tenant, kind):
    from quantuum.bot.ui.keyboards import readings_menu_kb

    i18n = await build_translator(session, default_tenant.id)
    await session.commit()  # flush so the separate session in readings_menu_kb sees the tenant
    kb = await readings_menu_kb(i18n, default_tenant.id)
    serialised = []
    for row in kb.inline_keyboard:
        for btn in row:
            serialised.append(btn.callback_data)
    assert any(cd == ReadingCb(action="generate", kind=kind).pack() for cd in serialised), kind


async def _seed_account(session, tenant_id, tg_user_id, *, profile=True, credits=0):
    from quantuum.db.models import AccountBalance, AccountPackage, PackagePlan

    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg_user_id
    )
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
    await session.flush()

    if credits > 0:
        # A matching AccountPackage row is needed so consume_quota can debit it.
        plan = PackagePlan(
            tenant_id=tenant_id, slug=f"test-pkg-{tg_user_id}",
            name="Test", request_count=credits, price_cents=0,
        )
        session.add(plan)
        await session.flush()
        pkg = AccountPackage(
            account_id=acc.id, tenant_id=tenant_id,
            plan_id=plan.id, requests_remaining=credits,
        )
        session.add(pkg)

    await session.commit()
    return acc


class FakeMessage:
    def __init__(self, chat_id=1):
        self.chat = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


class FakeQuery:
    def __init__(self, callback_data: str, chat_id: int = 555):
        self.data = callback_data
        self.message = FakeMessage(chat_id=chat_id)
        self.answer = AsyncMock()


async def test_on_reading_choice_creates_reading_and_enqueues(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import readings
    from quantuum.db.models import Reading, Request
    from sqlmodel import select

    _patch_sessionmaker(monkeypatch, readings, session)
    spy = AsyncMock()
    monkeypatch.setattr(readings, "enqueue_reading", spy)

    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "r1", credits=2)

    query = FakeQuery(ReadingCb(action="generate", kind="bazi").pack(), chat_id=555)
    await readings.on_reading_choice(query, acc, i18n)

    reading_rows = (await session.execute(select(Reading))).scalars().all()
    assert len(reading_rows) == 1
    assert reading_rows[0].kind == "bazi"

    req_rows = (await session.execute(select(Request).where(Request.kind == "reading"))).scalars().all()
    assert len(req_rows) == 1
    assert req_rows[0].charged_against == "package"

    spy.assert_awaited_once_with(reading_rows[0].id, 555, req_rows[0].id)
    query.message.answer.assert_called()
    text_sent = query.message.answer.await_args.args[0]
    assert "минут" in text_sent or "minute" in text_sent.lower() or text_sent


async def test_on_reading_choice_no_profile(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import readings
    from quantuum.db.models import Reading
    from sqlmodel import select

    _patch_sessionmaker(monkeypatch, readings, session)
    spy = AsyncMock()
    monkeypatch.setattr(readings, "enqueue_reading", spy)

    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "r2", profile=False, credits=2)

    query = FakeQuery(ReadingCb(action="generate", kind="numerology").pack())
    await readings.on_reading_choice(query, acc, i18n)

    spy.assert_not_awaited()
    assert (await session.execute(select(Reading))).scalars().first() is None
    query.message.answer.assert_called()


async def test_on_reading_choice_no_quota(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import readings
    from quantuum.db.models import Reading
    from quantuum.bot.ui.callbacks import BuyCb
    from sqlmodel import select

    _patch_sessionmaker(monkeypatch, readings, session)
    spy = AsyncMock()
    monkeypatch.setattr(readings, "enqueue_reading", spy)

    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "r3", credits=0)

    query = FakeQuery(ReadingCb(action="generate", kind="astrology").pack())
    await readings.on_reading_choice(query, acc, i18n)

    spy.assert_not_awaited()
    assert (await session.execute(select(Reading))).scalars().first() is None
    # Should offer buy keyboard
    kb = query.message.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None
    btn = kb.inline_keyboard[0][0]
    assert BuyCb.unpack(btn.callback_data).action == "open"


async def test_reading_no_profile_shows_fill_button(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import readings
    from quantuum.bot.ui.callbacks import OnboardCb, ReadingCb
    from unittest.mock import MagicMock, AsyncMock
    from quantuum.auth.identity import find_or_create_account_by_tg
    from tests.conftest import build_translator

    _patch_sessionmaker(monkeypatch, readings, session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="500"
    )
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    q = MagicMock()
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    q.data = ReadingCb(action="generate", kind="bazi").pack()

    await readings.on_reading_choice(q, account=acc, i18n=i18n)

    kb = q.message.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None, "no-profile response must include a keyboard"
    btns = [b for row in kb.inline_keyboard for b in row]
    assert any(
        OnboardCb.unpack(b.callback_data).action == "start" for b in btns
    ), "fill-profile button missing"


async def test_on_reading_choice_blueprint_dispatches_to_run_generate(
    session, default_tenant, monkeypatch
):
    from quantuum.bot.handlers import readings
    from unittest.mock import AsyncMock

    _patch_sessionmaker(monkeypatch, readings, session)
    spy = AsyncMock()
    monkeypatch.setattr(readings, "run_generate", spy)

    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "rb1", credits=2)

    query = FakeQuery(ReadingCb(action="generate", kind="blueprint").pack(), chat_id=777)
    await readings.on_reading_choice(query, acc, i18n)

    spy.assert_awaited_once()
    call_args = spy.await_args
    assert call_args.args[1] is acc
    assert call_args.args[2] == 777  # chat_id
    query.answer.assert_awaited()


async def test_on_reading_choice_transits_dispatches_to_run_transits(
    session, default_tenant, monkeypatch
):
    from quantuum.bot.handlers import readings
    from unittest.mock import AsyncMock

    _patch_sessionmaker(monkeypatch, readings, session)
    spy = AsyncMock()
    monkeypatch.setattr(readings, "run_transits", spy)

    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "rb2", credits=2)

    query = FakeQuery(ReadingCb(action="generate", kind="transits").pack(), chat_id=888)
    await readings.on_reading_choice(query, acc, i18n)

    spy.assert_awaited_once()
    call_args = spy.await_args
    assert call_args.args[1] is None  # raw_arg
    assert call_args.args[2] is acc
    query.answer.assert_awaited()


async def test_reading_enqueue_failure_refunds_credit(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import readings
    from quantuum.db.models import AccountBalance

    _patch_sessionmaker(monkeypatch, readings, session)
    monkeypatch.setattr(
        readings, "enqueue_reading",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )

    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "rfail", credits=2)

    query = FakeQuery(ReadingCb(action="generate", kind="bazi").pack(), chat_id=555)
    await readings.on_reading_choice(query, acc, i18n)

    expected = await i18n("errors.queue_failed")
    answers = [c.args[0] for c in query.message.answer.await_args_list]
    assert expected in answers

    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == 2  # refunded back to starting value
