from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.db.models import Account, AccountBalance, Payment, SubscriptionPlan


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


async def test_pick_records_pending_payment_and_sends_invoice(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import buy
    from quantuum.bot.ui.callbacks import BuyCb

    _patch_sessionmaker(monkeypatch, buy, session)

    acc = Account(tenant_id=default_tenant.id)
    plan = SubscriptionPlan(slug="m", name="Monthly", period_days=30, price_cents=250)
    session.add(acc)
    session.add(plan)
    await session.flush()

    bot = AsyncMock()
    query = AsyncMock()
    query.message = SimpleNamespace(chat=SimpleNamespace(id=4242))

    await buy.on_buy_pick(
        query, BuyCb(action="pick", kind="subscription", plan_id=plan.id), bot=bot, account=acc
    )

    bot.send_invoice.assert_awaited_once()
    kwargs = bot.send_invoice.await_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["chat_id"] == 4242
    assert kwargs["prices"][0].amount == 250

    from sqlmodel import select
    result = await session.execute(select(Payment).where(Payment.account_id == acc.id))
    pay = result.scalar_one()
    assert pay.status == "pending"
    assert pay.metadata_json == {"kind": "subscription", "plan_id": plan.id}
    assert kwargs["payload"] == str(pay.id)


async def test_pick_unknown_plan_alerts(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import buy
    from quantuum.bot.ui.callbacks import BuyCb

    _patch_sessionmaker(monkeypatch, buy, session)
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()

    bot = AsyncMock()
    query = AsyncMock()
    query.message = SimpleNamespace(chat=SimpleNamespace(id=1))
    await buy.on_buy_pick(query, BuyCb(action="pick", kind="package", plan_id=999), bot=bot, account=acc)

    bot.send_invoice.assert_not_awaited()
    query.answer.assert_awaited()


async def test_pre_checkout_answers_ok():
    from quantuum.bot.handlers import buy

    query = AsyncMock()
    await buy.on_pre_checkout(query)
    query.answer.assert_awaited_once_with(ok=True)


async def test_successful_payment_fulfills(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import buy
    from quantuum.domain.billing import record_pending_payment

    _patch_sessionmaker(monkeypatch, buy, session)
    acc = Account(tenant_id=default_tenant.id)
    plan = SubscriptionPlan(slug="m", name="Monthly", period_days=30, price_cents=250)
    session.add(acc)
    session.add(plan)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR", metadata={"kind": "subscription", "plan_id": plan.id},
    )

    message = SimpleNamespace(
        successful_payment=SimpleNamespace(
            invoice_payload=str(pay.id),
            telegram_payment_charge_id="charge_abc",
            total_amount=250,
            currency="XTR",
        ),
        answer=AsyncMock(),
    )
    await buy.on_successful_payment(message)

    await session.refresh(pay)
    assert pay.status == "paid"
    assert pay.external_id == "charge_abc"
    message.answer.assert_awaited_once()
    bal = await session.get(AccountBalance, acc.id)
    assert bal.subscription_active_until is not None
