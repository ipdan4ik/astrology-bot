from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import current_account, get_session
from quantuum.api.schemas import (
    BalanceOut,
    BlueprintCreatedOut,
    BlueprintOut,
    MeOut,
    NatalProfileIn,
    NatalProfileOut,
    PackagePlanOut,
    PaymentOut,
    PlansOut,
    SubscriptionOut,
    SubscriptionPlanOut,
)
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account, AccountBalance, AccountSubscription, Blueprint, Payment
from quantuum.domain.plans import list_package_plans, list_subscription_plans
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile
from quantuum.domain.quota import consume_quota, refund_quota
from quantuum.domain.requests import create_request
from quantuum.tasks import enqueue

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
async def get_me(account: Account = Depends(current_account)) -> MeOut:
    return MeOut(account_id=account.id, tenant_id=account.tenant_id)


@router.get("/natal-profile", response_model=NatalProfileOut)
async def read_natal_profile(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> NatalProfileOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="no natal profile")
    return NatalProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone=profile.timezone,
        for_year=profile.for_year,
    )


@router.put("/natal-profile", response_model=NatalProfileOut)
async def write_natal_profile(
    body: NatalProfileIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> NatalProfileOut:
    profile = await upsert_natal_profile(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        full_name=body.full_name,
        birth_date=body.birth_date,
        birth_time=body.birth_time,
        birth_place=body.birth_place,
        latitude=body.latitude,
        longitude=body.longitude,
        timezone=body.timezone,
        for_year=body.for_year,
    )
    return NatalProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone=profile.timezone,
        for_year=profile.for_year,
    )


@router.post("/blueprints", response_model=BlueprintCreatedOut, status_code=201)
async def create_blueprint_route(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BlueprintCreatedOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=409, detail="natal profile required")
    try:
        charged = await consume_quota(session, account.id, "blueprint")
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail="no quota; buy a plan") from exc

    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id, natal_profile_id=profile.id
    )
    request = await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    try:
        await enqueue.enqueue_blueprint(blueprint.id, None, request.id)
    except Exception as exc:
        await refund_quota(session, request.id)
        raise HTTPException(status_code=503, detail="could not enqueue; refunded") from exc
    return BlueprintCreatedOut(id=blueprint.id, status=blueprint.status)


@router.get("/blueprints", response_model=list[BlueprintOut])
async def list_blueprints(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[BlueprintOut]:
    result = await session.execute(
        select(Blueprint).where(Blueprint.account_id == account.id).order_by(Blueprint.id.desc())
    )
    return [
        BlueprintOut(
            id=bp.id,
            status=bp.status,
            created_at=bp.created_at.isoformat(),
            completed_at=bp.completed_at.isoformat() if bp.completed_at else None,
        )
        for bp in result.scalars().all()
    ]


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintOut)
async def read_blueprint(
    blueprint_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BlueprintOut:
    bp = await get_blueprint(session, blueprint_id)
    if bp.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    return BlueprintOut(
        id=bp.id,
        status=bp.status,
        created_at=bp.created_at.isoformat(),
        completed_at=bp.completed_at.isoformat() if bp.completed_at else None,
    )


@router.get("/blueprints/{blueprint_id}/download")
async def download_blueprint(
    blueprint_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> Response:
    bp = await get_blueprint(session, blueprint_id)
    if bp.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    if not bp.llm_md:
        raise HTTPException(status_code=409, detail="not ready")
    return Response(
        content=bp.llm_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="blueprint-{bp.id}.md"'},
    )


@router.get("/balance", response_model=BalanceOut)
async def get_balance(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BalanceOut:
    balance = await session.get(AccountBalance, account.id)
    if balance is None:
        return BalanceOut(free_trial_used=False, subscription_active_until=None, package_credits=0)
    return BalanceOut(
        free_trial_used=balance.free_trial_used,
        subscription_active_until=(
            balance.subscription_active_until.isoformat()
            if balance.subscription_active_until
            else None
        ),
        package_credits=balance.package_credits,
    )


@router.get("/plans", response_model=PlansOut)
async def get_plans(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> PlansOut:
    subs = await list_subscription_plans(session, tenant_id=account.tenant_id)
    pkgs = await list_package_plans(session, tenant_id=account.tenant_id)
    return PlansOut(
        subscriptions=[
            SubscriptionPlanOut(
                id=s.id, slug=s.slug, name=s.name, period_days=s.period_days,
                price_cents=s.price_cents, currency=s.currency,
            )
            for s in subs
        ],
        packages=[
            PackagePlanOut(
                id=p.id, slug=p.slug, name=p.name, request_count=p.request_count,
                price_cents=p.price_cents, currency=p.currency,
                expires_after_days=p.expires_after_days,
            )
            for p in pkgs
        ],
    )


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionOut]:
    result = await session.execute(
        select(AccountSubscription)
        .where(AccountSubscription.account_id == account.id)
        .order_by(AccountSubscription.id.desc())
    )
    return [
        SubscriptionOut(
            id=s.id, plan_id=s.plan_id, status=s.status,
            started_at=s.started_at.isoformat(), ends_at=s.ends_at.isoformat(),
        )
        for s in result.scalars().all()
    ]


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentOut]:
    result = await session.execute(
        select(Payment).where(Payment.account_id == account.id).order_by(Payment.id.desc())
    )
    return [
        PaymentOut(
            id=p.id, amount_cents=p.amount_cents, currency=p.currency, status=p.status,
            created_at=p.created_at.isoformat(),
            paid_at=p.paid_at.isoformat() if p.paid_at else None,
        )
        for p in result.scalars().all()
    ]
