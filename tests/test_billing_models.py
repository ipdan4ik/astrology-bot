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
