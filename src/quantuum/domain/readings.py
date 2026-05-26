from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.db.models import Reading

_TERMINAL = {"done", "failed"}


async def create_reading(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int,
    kind: str, lang: str | None = None,
) -> Reading:
    reading = Reading(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        kind=kind,
        lang=lang,
        status="pending",
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    return reading


async def get_reading(session, reading_id: int) -> Reading:
    reading = await session.get(Reading, reading_id)
    if reading is None:
        raise NotFoundError("reading not found")
    return reading


async def set_reading_status(session, reading_id: int, status: str, **fields) -> None:
    reading = await get_reading(session, reading_id)
    reading.status = status
    for key, value in fields.items():
        setattr(reading, key, value)
    if status in _TERMINAL:
        reading.completed_at = utcnow()
    session.add(reading)
    await session.commit()


async def list_readings(
    session, *, account_id: int, limit: int = 50, offset: int = 0
) -> list[Reading]:
    result = await session.execute(
        select(Reading)
        .where(Reading.account_id == account_id)
        .order_by(Reading.created_at.desc(), Reading.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
