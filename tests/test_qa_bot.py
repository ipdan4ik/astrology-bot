"""Handler-level tests for the /ask Q&A astrologer flow.

Mirrors tests/test_generate_no_quota_offer.py (sessionmaker patching + buy-offer
keyboard assertions) and the fake Message / FSM patterns from
tests/test_bot_start_menu_profile.py.
"""
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.models import AccountBalance, QaAnswer, Request
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


class FakeFSM:
    """Dict-backed stand-in for aiogram's FSMContext."""

    def __init__(self):
        self._data = {}
        self._state = None

    async def set_state(self, state):
        self._state = state

    async def get_state(self):
        return self._state

    async def clear(self):
        self._data = {}
        self._state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)
        return dict(self._data)


async def _seed_account(session, tenant_id, tg_user_id, *, profile=True, credits=0):
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
    await session.commit()
    return acc


async def test_ask_with_quota_consumes_and_enqueues(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa

    _patch_sessionmaker(monkeypatch, qa, session)
    spy = AsyncMock()
    monkeypatch.setattr(qa, "enqueue_qa", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "100", credits=2)

    msg = FakeMessage(text="/ask Что меня ждёт?", chat_id=100)
    command = SimpleNamespace(args="Что меня ждёт?")
    await qa.on_ask(msg, command, FakeFSM(), acc, i18n)

    # qa row + request row created
    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
    assert len(qa_rows) == 1
    assert qa_rows[0].question == "Что меня ждёт?"
    req_rows = (await session.execute(select(Request).where(Request.kind == "qa"))).scalars().all()
    assert len(req_rows) == 1
    assert req_rows[0].charged_against == "package"

    # quota decremented
    balance = await session.get(AccountBalance, acc.id)
    assert balance.package_credits == 1

    spy.assert_awaited_once_with(qa_rows[0].id, 100, req_rows[0].id)
    text = msg.answer.await_args.args[0]
    assert text == "Думаю над ответом… ⏳"


async def test_ask_no_quota_offers_buy_button(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa

    _patch_sessionmaker(monkeypatch, qa, session)
    spy = AsyncMock()
    monkeypatch.setattr(qa, "enqueue_qa", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "101", credits=0)

    msg = FakeMessage(text="/ask hello?", chat_id=101)
    command = SimpleNamespace(args="hello?")
    await qa.on_ask(msg, command, FakeFSM(), acc, i18n)

    text = msg.answer.await_args.args[0]
    assert text == "Закончились разборы. Купи пакет или подписку, чтобы спрашивать астролога:"
    kb = msg.answer.await_args.kwargs["reply_markup"]
    btn = kb.inline_keyboard[0][0]
    assert BuyCb.unpack(btn.callback_data).action == "open"

    spy.assert_not_awaited()
    assert (await session.execute(select(QaAnswer))).scalars().first() is None


async def test_ask_no_profile(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa

    _patch_sessionmaker(monkeypatch, qa, session)
    spy = AsyncMock()
    monkeypatch.setattr(qa, "enqueue_qa", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "102", profile=False, credits=2)

    msg = FakeMessage(text="/ask hello?", chat_id=102)
    command = SimpleNamespace(args="hello?")
    await qa.on_ask(msg, command, FakeFSM(), acc, i18n)

    text = msg.answer.await_args.args[0]
    assert "натальный профиль" in text
    spy.assert_not_awaited()
    # no quota consumed
    balance = await session.get(AccountBalance, acc.id)
    assert balance.package_credits == 2
    assert (await session.execute(select(QaAnswer))).scalars().first() is None


async def test_ask_fsm_prompt_then_submit(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa

    _patch_sessionmaker(monkeypatch, qa, session)
    spy = AsyncMock()
    monkeypatch.setattr(qa, "enqueue_qa", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "103", credits=2)

    state = FakeFSM()
    # /ask with no args -> set state + prompt
    msg = FakeMessage(text="/ask", chat_id=103)
    command = SimpleNamespace(args=None)
    await qa.on_ask(msg, command, state, acc, i18n)

    assert await state.get_state() == qa.Ask.awaiting_question
    assert msg.answer.await_args.args[0] == "Напиши свой вопрос астрологу:"
    assert (await session.execute(select(QaAnswer))).scalars().first() is None

    # follow-up question -> submit
    msg2 = FakeMessage(text="Когда повезёт?", chat_id=103)
    await qa.on_ask_question(msg2, state, acc, i18n)

    assert await state.get_state() is None
    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
    assert len(qa_rows) == 1
    assert qa_rows[0].question == "Когда повезёт?"
    spy.assert_awaited_once()
    assert msg2.answer.await_args.args[0] == "Думаю над ответом… ⏳"


async def test_ask_too_long(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa

    _patch_sessionmaker(monkeypatch, qa, session)
    spy = AsyncMock()
    monkeypatch.setattr(qa, "enqueue_qa", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "104", credits=2)

    msg = FakeMessage(text="/ask " + "x" * 1001, chat_id=104)
    command = SimpleNamespace(args="x" * 1001)
    await qa.on_ask(msg, command, FakeFSM(), acc, i18n)

    text = msg.answer.await_args.args[0]
    assert text == "Вопрос слишком длинный (макс 1000 символов)."
    spy.assert_not_awaited()
    assert (await session.execute(select(QaAnswer))).scalars().first() is None


async def test_ask_empty(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa

    _patch_sessionmaker(monkeypatch, qa, session)
    spy = AsyncMock()
    monkeypatch.setattr(qa, "enqueue_qa", spy)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "105", credits=2)

    state = FakeFSM()
    msg = FakeMessage(text="   ", chat_id=105)
    await qa.on_ask_question(msg, state, acc, i18n)

    text = msg.answer.await_args.args[0]
    assert text == "Вопрос пустой. Напиши вопрос:"
    spy.assert_not_awaited()
    assert (await session.execute(select(QaAnswer))).scalars().first() is None


async def test_start_ask_prompt_has_cancel_button(session, default_tenant):
    from quantuum.bot.handlers import qa
    from quantuum.bot.ui.callbacks import OnboardCb

    i18n = await build_translator(session, default_tenant.id)
    state = FakeFSM()
    msg = FakeMessage(text="/ask", chat_id=200)
    await qa.start_ask(msg, state, i18n)

    assert await state.get_state() == qa.Ask.awaiting_question
    kb = msg.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None, "start_ask must attach a keyboard"
    btns = [b for row in kb.inline_keyboard for b in row]
    actions = [OnboardCb.unpack(b.callback_data).action for b in btns]
    assert "cancel" in actions


async def test_ask_no_profile_shows_fill_button(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import qa
    from quantuum.bot.ui.callbacks import OnboardCb

    _patch_sessionmaker(monkeypatch, qa, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed_account(session, default_tenant.id, "510", profile=False, credits=2)

    msg = FakeMessage(text="/ask hello?", chat_id=510)
    command = SimpleNamespace(args="hello?")
    await qa.on_ask(msg, command, FakeFSM(), acc, i18n)

    kb = msg.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None, "no-profile response must include a keyboard"
    btns = [b for row in kb.inline_keyboard for b in row]
    assert any(OnboardCb.unpack(b.callback_data).action == "start" for b in btns)
