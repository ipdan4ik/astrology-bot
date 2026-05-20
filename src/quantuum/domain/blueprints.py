from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.db.models import Blueprint

_TERMINAL = {"done", "failed"}


async def create_blueprint(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int
) -> Blueprint:
    blueprint = Blueprint(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        status="pending",
    )
    session.add(blueprint)
    await session.commit()
    await session.refresh(blueprint)
    return blueprint


async def get_blueprint(session, blueprint_id: int) -> Blueprint:
    blueprint = await session.get(Blueprint, blueprint_id)
    if blueprint is None:
        raise NotFoundError("blueprint not found")
    return blueprint


async def set_status(session, blueprint_id: int, status: str, **fields) -> None:
    blueprint = await get_blueprint(session, blueprint_id)
    blueprint.status = status
    for key, value in fields.items():
        setattr(blueprint, key, value)
    if status in _TERMINAL:
        blueprint.completed_at = utcnow()
    session.add(blueprint)
    await session.commit()
