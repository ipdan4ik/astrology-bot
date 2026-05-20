from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import current_account, get_session
from quantuum.api.schemas import BlueprintCreatedOut, BlueprintOut, MeOut, NatalProfileIn, NatalProfileOut
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account, Blueprint
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile
from quantuum.domain.quota import consume_quota
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
    await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    await enqueue.enqueue_blueprint(blueprint.id, None)
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
