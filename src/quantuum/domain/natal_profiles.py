from datetime import date, time
from decimal import Decimal

from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import NatalProfile


async def get_natal_profile(session, account_id: int) -> NatalProfile | None:
    result = await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == account_id)
    )
    return result.scalar_one_or_none()


async def upsert_natal_profile(
    session,
    *,
    tenant_id: int,
    account_id: int,
    full_name: str,
    birth_date: date,
    birth_time: time,
    birth_place: str,
    latitude: Decimal,
    longitude: Decimal,
    timezone: str,
    for_year: int | None = None,
) -> NatalProfile:
    profile = await get_natal_profile(session, account_id)
    if profile is None:
        profile = NatalProfile(tenant_id=tenant_id, account_id=account_id, full_name=full_name,
                               birth_date=birth_date, birth_time=birth_time, birth_place=birth_place,
                               latitude=latitude, longitude=longitude, timezone=timezone,
                               for_year=for_year)
    else:
        profile.full_name = full_name
        profile.birth_date = birth_date
        profile.birth_time = birth_time
        profile.birth_place = birth_place
        profile.latitude = latitude
        profile.longitude = longitude
        profile.timezone = timezone
        profile.for_year = for_year
        profile.updated_at = utcnow()
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile
