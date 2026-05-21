from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.domain.natal_profiles import upsert_natal_profile


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

    _patch_sessionmaker(monkeypatch, gen, session)
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="9")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    # burn the free trial
    monkeypatch.setattr(gen, "enqueue_blueprint", AsyncMock())
    await gen.run_generate(SimpleNamespace(answer=AsyncMock()), acc, chat_id=9)

    message = SimpleNamespace(answer=AsyncMock())
    await gen.run_generate(message, acc, chat_id=9)

    message.answer.assert_awaited()
    kb = message.answer.await_args.kwargs["reply_markup"]
    cb = BuyCb.unpack(kb.inline_keyboard[0][0].callback_data)
    assert cb.action == "open"
