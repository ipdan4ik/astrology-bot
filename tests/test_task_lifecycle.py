from datetime import timedelta
from unittest.mock import AsyncMock

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountIdentity,
    AccountSubscription,
    SubscriptionPlan,
    TenantBot,
)


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


async def test_lifecycle_task_sends_reminder_and_marks(session, default_tenant, monkeypatch):
    import quantuum.tasks.lifecycle as lc

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id="555"))
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    sub = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow() - timedelta(days=28),
        ends_at=utcnow() + timedelta(days=2),
    )
    session.add(sub)
    # an active tenant bot so the pool resolves this tenant
    session.add(TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=10, bot_token_enc=b"x",
        webhook_secret_path="wh-10", status="active",
    ))
    await session.commit()
    await session.refresh(sub)

    fake_bot = AsyncMock()
    monkeypatch.setattr(lc, "build_bots_by_tenant", lambda rows: {default_tenant.id: fake_bot})

    ctx = {"sessionmaker": _Maker(session)}
    await lc.subscription_lifecycle(ctx)

    fake_bot.send_message.assert_awaited_once()
    chat_id = fake_bot.send_message.await_args.args[0]
    assert chat_id == 555
    await session.refresh(sub)
    assert sub.reminder_sent_at is not None


async def test_lifecycle_task_no_due_is_safe(session, monkeypatch):
    import quantuum.tasks.lifecycle as lc

    monkeypatch.setattr(lc, "build_bots_by_tenant", lambda rows: {})
    ctx = {"sessionmaker": _Maker(session)}
    await lc.subscription_lifecycle(ctx)  # no exception
