"""DB-backed LLM configuration helpers.

Keys stored in platform_config as  llm.<field>  with value_jsonb = {"value": <v>}.
The API key is NEVER stored or returned — it stays env-only.
"""

from sqlmodel import select

from quantuum.db.models import PlatformConfig
from quantuum.settings import get_settings

LLM_FIELDS = ("provider", "model", "temperature", "max_tokens")
_COERCE: dict = {
    "provider": str,
    "model": str,
    "temperature": float,
    "max_tokens": int,
}


async def get_llm_config(session) -> dict:
    """Return the effective LLM config: settings defaults overridden by any DB rows."""
    s = get_settings()
    cfg: dict = {
        "provider": s.llm_provider,
        "model": s.llm_model,
        "temperature": s.llm_temperature,
        "max_tokens": s.llm_max_tokens,
    }
    keys = [f"llm.{k}" for k in LLM_FIELDS]
    result = await session.execute(
        select(PlatformConfig).where(PlatformConfig.key.in_(keys))
    )
    for row in result.scalars().all():
        field = row.key.removeprefix("llm.")
        if field in LLM_FIELDS:
            raw = (row.value_jsonb or {}).get("value")
            if raw is not None:
                cfg[field] = _COERCE[field](raw)
    return cfg


async def set_llm_config(
    session, *, actor_id: int | None = None, **fields
) -> dict:
    """Upsert the provided LLM fields into platform_config.

    Only fields whose names are in LLM_FIELDS and whose values are not None
    are written.  Returns the new effective config (via get_llm_config).
    """
    from quantuum.common.datetime import utcnow

    for field, value in fields.items():
        if field not in LLM_FIELDS or value is None:
            continue
        key = f"llm.{field}"
        existing = await session.get(PlatformConfig, key)
        if existing is None:
            session.add(
                PlatformConfig(
                    key=key,
                    value_jsonb={"value": value},
                    updated_by_account_id=actor_id,
                )
            )
        else:
            # Assign a new dict to trigger SQLAlchemy JSONB change detection.
            existing.value_jsonb = {"value": value}
            existing.updated_by_account_id = actor_id
            existing.updated_at = utcnow()
            session.add(existing)
    await session.flush()
    return await get_llm_config(session)
