from quantuum.db.bootstrap import ensure_global_plans
from quantuum.domain.plans import (
    get_package_plan,
    get_subscription_plan,
    list_package_plans,
    list_subscription_plans,
)


async def test_ensure_global_plans_idempotent(session):
    await ensure_global_plans(session)
    await ensure_global_plans(session)  # idempotent

    subs = await list_subscription_plans(session, tenant_id=None)
    pkgs = await list_package_plans(session, tenant_id=None)
    assert {s.slug for s in subs} == {"monthly"}
    assert {p.slug for p in pkgs} == {"pack_small", "pack_large"}


async def test_list_plans_unions_global_and_tenant(session, default_tenant):
    from quantuum.db.models import SubscriptionPlan

    await ensure_global_plans(session)
    session.add(
        SubscriptionPlan(tenant_id=default_tenant.id, slug="custom", name="Custom",
                         period_days=7, price_cents=99)
    )
    await session.commit()

    subs = await list_subscription_plans(session, tenant_id=default_tenant.id)
    slugs = {s.slug for s in subs}
    assert "monthly" in slugs  # global
    assert "custom" in slugs  # tenant-specific


async def test_get_plan_only_active(session):
    from quantuum.db.models import SubscriptionPlan

    p = SubscriptionPlan(slug="dead", name="Dead", period_days=30, price_cents=1, active=False)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert await get_subscription_plan(session, p.id) is None  # inactive not returned


async def test_get_package_plan(session):
    from quantuum.db.models import PackagePlan

    p = PackagePlan(slug="x", name="X", request_count=3, price_cents=10)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    got = await get_package_plan(session, p.id)
    assert got is not None and got.request_count == 3
