from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import BuyCb
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


async def test_no_quota_offers_buy_button(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import generate as gen
    from quantuum.db.models import AccountBalance

    _patch_sessionmaker(monkeypatch, gen, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="9")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    # burn one credit, then zero out remaining credits to force no-quota on next call
    monkeypatch.setattr(gen, "enqueue_blueprint", AsyncMock())
    await gen.run_generate(SimpleNamespace(answer=AsyncMock()), acc, chat_id=9, i18n=i18n)
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = 0
    session.add(bal)
    await session.commit()

    message = SimpleNamespace(answer=AsyncMock())
    await gen.run_generate(message, acc, chat_id=9, i18n=i18n)

    message.answer.assert_awaited()
    text = message.answer.await_args.args[0]
    assert text == "Бесплатная генерация уже использована. Купи пакет разборов или подписку:"
    kb = message.answer.await_args.kwargs["reply_markup"]
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "💳 Купить разборы"
    cb = BuyCb.unpack(btn.callback_data)
    assert cb.action == "open"


async def test_no_quota_offers_buy_button_en(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import generate as gen
    from quantuum.db.models import AccountBalance

    _patch_sessionmaker(monkeypatch, gen, session)
    i18n = await build_translator(session, default_tenant.id, lang="en")
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="19")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    # burn one credit, then zero out remaining credits to force no-quota on next call
    monkeypatch.setattr(gen, "enqueue_blueprint", AsyncMock())
    await gen.run_generate(SimpleNamespace(answer=AsyncMock()), acc, chat_id=19, i18n=i18n)
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = 0
    session.add(bal)
    await session.commit()

    message = SimpleNamespace(answer=AsyncMock())
    await gen.run_generate(message, acc, chat_id=19, i18n=i18n)

    text = message.answer.await_args.args[0]
    assert text == "Your free generation has already been used. Buy a package or subscription:"
    kb = message.answer.await_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].text == "💳 Buy readings"
