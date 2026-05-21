from sqlmodel import or_, select

from quantuum.db.models import PackagePlan, SubscriptionPlan


async def list_subscription_plans(session, *, tenant_id: int | None) -> list[SubscriptionPlan]:
    query = select(SubscriptionPlan).where(SubscriptionPlan.active == True)  # noqa: E712
    if tenant_id is None:
        query = query.where(SubscriptionPlan.tenant_id.is_(None))
    else:
        query = query.where(
            or_(SubscriptionPlan.tenant_id.is_(None), SubscriptionPlan.tenant_id == tenant_id)
        )
    result = await session.execute(query.order_by(SubscriptionPlan.id))
    return list(result.scalars().all())


async def list_package_plans(session, *, tenant_id: int | None) -> list[PackagePlan]:
    query = select(PackagePlan).where(PackagePlan.active == True)  # noqa: E712
    if tenant_id is None:
        query = query.where(PackagePlan.tenant_id.is_(None))
    else:
        query = query.where(
            or_(PackagePlan.tenant_id.is_(None), PackagePlan.tenant_id == tenant_id)
        )
    result = await session.execute(query.order_by(PackagePlan.id))
    return list(result.scalars().all())


async def get_subscription_plan(session, plan_id: int) -> SubscriptionPlan | None:
    plan = await session.get(SubscriptionPlan, plan_id)
    return plan if plan is not None and plan.active else None


async def get_package_plan(session, plan_id: int) -> PackagePlan | None:
    plan = await session.get(PackagePlan, plan_id)
    return plan if plan is not None and plan.active else None
