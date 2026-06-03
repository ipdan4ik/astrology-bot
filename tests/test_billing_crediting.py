from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountPackage,
    PackagePlan,
    SubscriptionPlan,
)
from quantuum.domain.billing import (
    apply_package_payment,
    apply_subscription_payment,
    recompute_account_balance,
)


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    return acc


async def test_apply_subscription_payment_sets_balance(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()

    sub = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    assert sub.status == "active"
    bal = await session.get(AccountBalance, acc.id)
    assert bal.subscription_active_until is not None
    assert bal.subscription_active_until > utcnow() + timedelta(days=29)


async def test_renewal_extends_existing_subscription(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()

    sub1 = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    first_end = sub1.ends_at
    sub2 = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    assert sub2.id == sub1.id  # same row, extended (no duplicate active sub)
    assert sub2.ends_at > first_end
    assert sub2.renewed_at is not None


async def test_apply_package_payment_credits(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=400)
    session.add(plan)
    await session.flush()

    await apply_package_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5

    await apply_package_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 10  # two packages summed


async def test_recompute_excludes_expired_packages(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=1)
    session.add(plan)
    await session.flush()
    session.add(AccountPackage(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        requests_remaining=5, expires_at=utcnow() - timedelta(days=1),
    ))
    session.add(AccountPackage(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        requests_remaining=3, expires_at=None,
    ))
    await session.commit()

    bal = await recompute_account_balance(session, acc.id)
    assert bal.package_credits == 3  # expired pack excluded


async def test_renewal_resets_reminder_sent_at(session, default_tenant):
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import SubscriptionPlan
    from quantuum.domain.billing import apply_subscription_payment

    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()

    sub1 = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    sub1.reminder_sent_at = utcnow()
    session.add(sub1)
    await session.commit()

    sub2 = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    assert sub2.id == sub1.id
    assert sub2.reminder_sent_at is None  # renewal re-arms the reminder


async def test_apply_subscription_payment_scopes_dedup_by_tenant(session, default_tenant):
    from datetime import timedelta
    from sqlalchemy import select
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import (
        Account, AccountSubscription, SubscriptionPlan, Tenant,
    )
    from quantuum.domain.billing import apply_subscription_payment

    other = Tenant(slug="other-sub", display_name="Other")
    session.add(other)
    await session.flush()

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    plan = SubscriptionPlan(
        tenant_id=default_tenant.id, slug="pro-dedup", name="Pro", price_cents=500,
        period_days=30, currency="XTR",
    )
    session.add(plan)
    await session.flush()

    # Pre-existing active sub for the SAME account+plan but the WRONG tenant.
    stale = AccountSubscription(
        tenant_id=other.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow(),
        ends_at=utcnow() + timedelta(days=30),
    )
    session.add(stale)
    await session.commit()

    await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id,
        plan=plan, payment_id=None,
    )

    subs = (
        await session.execute(
            select(AccountSubscription).where(AccountSubscription.account_id == acc.id)
        )
    ).scalars().all()
    # A new sub for the correct tenant must exist; the stale one is untouched.
    assert len(subs) == 2
    assert any(s.tenant_id == default_tenant.id for s in subs)
    assert any(s.tenant_id == other.id for s in subs)
