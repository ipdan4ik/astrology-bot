from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import current_account, get_session
from quantuum.api.schemas import MeOut, NatalProfileIn, NatalProfileOut
from quantuum.db.models import Account
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile

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
