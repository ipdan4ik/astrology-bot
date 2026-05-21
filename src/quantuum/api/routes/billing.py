from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_superadmin
from quantuum.api.schemas import (
    PackagePlanAdminOut,
    PackagePlanCreateIn,
    PackagePlanPatchIn,
    SubscriptionPlanAdminOut,
    SubscriptionPlanCreateIn,
    SubscriptionPlanPatchIn,
)
from quantuum.db.models import Account, PackagePlan, SubscriptionPlan

router = APIRouter(prefix="/admin/platform/plans", tags=["admin-plans"])


def _sub_out(p: SubscriptionPlan) -> SubscriptionPlanAdminOut:
    return SubscriptionPlanAdminOut(
        id=p.id, slug=p.slug, name=p.name, period_days=p.period_days,
        price_cents=p.price_cents, currency=p.currency, active=p.active, tenant_id=p.tenant_id,
    )


def _pkg_out(p: PackagePlan) -> PackagePlanAdminOut:
    return PackagePlanAdminOut(
        id=p.id, slug=p.slug, name=p.name, request_count=p.request_count,
        price_cents=p.price_cents, currency=p.currency, expires_after_days=p.expires_after_days,
        active=p.active, tenant_id=p.tenant_id,
    )


@router.post("/subscriptions", response_model=SubscriptionPlanAdminOut, status_code=201)
async def create_subscription_plan(
    body: SubscriptionPlanCreateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionPlanAdminOut:
    plan = SubscriptionPlan(
        tenant_id=body.tenant_id, slug=body.slug, name=body.name,
        period_days=body.period_days, price_cents=body.price_cents, currency=body.currency,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _sub_out(plan)


@router.get("/subscriptions", response_model=list[SubscriptionPlanAdminOut])
async def list_all_subscription_plans(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionPlanAdminOut]:
    result = await session.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.id))
    return [_sub_out(p) for p in result.scalars().all()]


@router.patch("/subscriptions/{plan_id}", response_model=SubscriptionPlanAdminOut)
async def patch_subscription_plan(
    plan_id: int,
    body: SubscriptionPlanPatchIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionPlanAdminOut:
    plan = await session.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _sub_out(plan)


@router.post("/packages", response_model=PackagePlanAdminOut, status_code=201)
async def create_package_plan(
    body: PackagePlanCreateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PackagePlanAdminOut:
    plan = PackagePlan(
        tenant_id=body.tenant_id, slug=body.slug, name=body.name,
        request_count=body.request_count, price_cents=body.price_cents,
        currency=body.currency, expires_after_days=body.expires_after_days,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _pkg_out(plan)


@router.get("/packages", response_model=list[PackagePlanAdminOut])
async def list_all_package_plans(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[PackagePlanAdminOut]:
    result = await session.execute(select(PackagePlan).order_by(PackagePlan.id))
    return [_pkg_out(p) for p in result.scalars().all()]


@router.patch("/packages/{plan_id}", response_model=PackagePlanAdminOut)
async def patch_package_plan(
    plan_id: int,
    body: PackagePlanPatchIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PackagePlanAdminOut:
    plan = await session.get(PackagePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _pkg_out(plan)
