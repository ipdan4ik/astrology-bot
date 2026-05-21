from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountSubscription,
    SubscriptionPlan,
)
from quantuum.domain.billing import GRACE_DAYS, recompute_account_balance


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    return acc


async def test_grace_subscription_extends_access_by_grace_days(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    ended = utcnow() - timedelta(hours=1)  # already past ends_at
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="grace", started_at=ended - timedelta(days=30), ends_at=ended,
    ))
    await session.commit()

    bal = await recompute_account_balance(session, acc.id)
    # grace still grants access: active_until ≈ ends_at + GRACE_DAYS (in the future)
    assert bal.subscription_active_until is not None
    assert bal.subscription_active_until > utcnow()
    assert bal.subscription_active_until <= ended + timedelta(days=GRACE_DAYS) + timedelta(seconds=1)


async def test_active_subscription_access_is_ends_at(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    ends = utcnow() + timedelta(days=10)
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow(), ends_at=ends,
    ))
    await session.commit()

    bal = await recompute_account_balance(session, acc.id)
    assert abs((bal.subscription_active_until - ends).total_seconds()) < 1  # no grace added
