from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.db.models import TenantConfig

FEATURE_KEYS: tuple[str, ...] = (
    "qa",
    "blueprint",
    "transits",
    "daily",
    "reading.bazi",
    "reading.numerology",
    "reading.human_design",
    "reading.astrology",
    "reading.vedic",
    "reading.gene_keys",
    "reading.mayan",
    "reading.aspects",
)

_CONFIG_KEY_PREFIX = "feature."


def _config_key(feature_key: str) -> str:
    return f"{_CONFIG_KEY_PREFIX}{feature_key}"


async def is_feature_enabled(
    session: AsyncSession, tenant_id: int, key: str
) -> bool:
    """Resolve a single feature flag. Missing row => True (default ON)."""
    row = await session.get(TenantConfig, (tenant_id, _config_key(key)))
    if row is None:
        return True
    return bool(row.value_jsonb.get("enabled", True))


async def list_feature_states(
    session: AsyncSession, tenant_id: int
) -> dict[str, bool]:
    """Return {feature_key: enabled} for all 12 features."""
    stmt = select(TenantConfig).where(
        TenantConfig.tenant_id == tenant_id,
        TenantConfig.key.like(f"{_CONFIG_KEY_PREFIX}%"),
    )
    rows = (await session.execute(stmt)).scalars().all()
    overrides = {
        row.key.removeprefix(_CONFIG_KEY_PREFIX): bool(
            row.value_jsonb.get("enabled", True)
        )
        for row in rows
    }
    return {k: overrides.get(k, True) for k in FEATURE_KEYS}


async def set_feature_enabled(
    session: AsyncSession,
    *,
    tenant_id: int,
    key: str,
    enabled: bool,
    by_account_id: int,
) -> None:
    """Upsert the override row. Raises ValueError for unknown feature keys."""
    if key not in FEATURE_KEYS:
        raise ValueError(f"unknown feature key: {key}")
    row = await session.get(TenantConfig, (tenant_id, _config_key(key)))
    if row is None:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=_config_key(key),
            value_jsonb={"enabled": enabled},
            updated_by_account_id=by_account_id,
        )
        session.add(row)
    else:
        row.value_jsonb = {"enabled": enabled}
        row.updated_by_account_id = by_account_id
    await session.flush()
