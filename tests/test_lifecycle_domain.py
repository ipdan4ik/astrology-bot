from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountIdentity,
    AccountSubscription,
    SubscriptionPlan,
)
from quantuum.domain.lifecycle import (
    due_renewal_reminders,
    mark_reminder_sent,
    sweep_subscriptions,
)


async def _acc_with_chat(session, default_tenant, tg_id: str):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg_id))
    await session.flush()
    return acc


async def test_sweep_active_to_grace_and_grace_to_expired(session, default_tenant):
    acc = await _acc_with_chat(session, default_tenant, "100")
    plan_a = SubscriptionPlan(slug="ma", name="MA", period_days=30, price_cents=1)
    plan_b = SubscriptionPlan(slug="mb", name="MB", period_days=30, price_cents=1)
    session.add(plan_a)
    session.add(plan_b)
    await session.flush()
    now = utcnow()
    # active but past ends_at → should become grace
    s_grace = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan_a.id,
        status="active", started_at=now - timedelta(days=31), ends_at=now - timedelta(hours=1),
    )
    # grace past the grace window → should become expired
    s_expired = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan_b.id,
        status="grace", started_at=now - timedelta(days=40),
        ends_at=now - timedelta(days=10),
    )
    session.add(s_grace)
    session.add(s_expired)
    await session.commit()

    await sweep_subscriptions(session)

    await session.refresh(s_grace)
    await session.refresh(s_expired)
    assert s_grace.status == "grace"
    assert s_expired.status == "expired"


async def test_due_renewal_reminders_and_mark(session, default_tenant):
    acc = await _acc_with_chat(session, default_tenant, "200")
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    now = utcnow()
    sub = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=now - timedelta(days=28),
        ends_at=now + timedelta(days=2),  # within REMINDER_DAYS (3)
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)

    due = await due_renewal_reminders(session)
    assert len(due) == 1
    item = due[0]
    assert item.sub_id == sub.id
    assert item.tenant_id == default_tenant.id
    assert item.chat_id == "200"

    await mark_reminder_sent(session, sub.id)
    # not due again once reminded
    assert await due_renewal_reminders(session) == []


async def test_reminder_not_due_when_far_out(session, default_tenant):
    acc = await _acc_with_chat(session, default_tenant, "300")
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow(), ends_at=utcnow() + timedelta(days=20),
    ))
    await session.commit()
    assert await due_renewal_reminders(session) == []
