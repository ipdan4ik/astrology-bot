from quantuum.db.models import PackagePlan, SubscriptionPlan


async def test_subscription_plan_defaults(session):
    p = SubscriptionPlan(slug="monthly", name="Monthly", period_days=30, price_cents=250)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.currency == "XTR"
    assert p.active is True
    assert p.tenant_id is None  # global by default


async def test_package_plan_defaults(session):
    p = PackagePlan(slug="pack_small", name="Small", request_count=5, price_cents=400)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.expires_after_days is None
    assert p.currency == "XTR"
    assert p.active is True


async def test_payment_and_account_billing_rows(session, default_tenant):
    from quantuum.db.models import (
        Account,
        AccountPackage,
        AccountSubscription,
        PackagePlan,
        Payment,
        PaymentProvider,
        SubscriptionPlan,
    )
    from quantuum.common.datetime import utcnow

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()

    provider = PaymentProvider(tenant_id=default_tenant.id, kind="tg_stars", config_enc=b"")
    session.add(provider)
    await session.flush()

    pay = Payment(
        tenant_id=default_tenant.id, account_id=acc.id, provider_id=provider.id,
        amount_cents=250, currency="XTR", status="pending", metadata_json={"plan": "monthly"},
    )
    session.add(pay)
    await session.flush()
    assert pay.id is not None
    assert pay.metadata_json == {"plan": "monthly"}

    sub_plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    pkg_plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=400)
    session.add(sub_plan)
    session.add(pkg_plan)
    await session.flush()

    sub = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=sub_plan.id,
        status="active", started_at=utcnow(), ends_at=utcnow(),
    )
    pkg = AccountPackage(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=pkg_plan.id,
        requests_remaining=5, payment_id=pay.id,
    )
    session.add(sub)
    session.add(pkg)
    await session.commit()
    assert sub.id is not None and pkg.id is not None


async def test_active_subscription_partial_unique(session, default_tenant):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from quantuum.common.datetime import utcnow
    from quantuum.db.models import Account, AccountSubscription, SubscriptionPlan

    acc = Account(tenant_id=default_tenant.id)
    plan = SubscriptionPlan(slug="m2", name="M2", period_days=30, price_cents=1)
    session.add(acc)
    session.add(plan)
    await session.flush()

    common = dict(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                  started_at=utcnow(), ends_at=utcnow())
    session.add(AccountSubscription(status="active", **common))
    await session.commit()
    session.add(AccountSubscription(status="grace", **common))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
