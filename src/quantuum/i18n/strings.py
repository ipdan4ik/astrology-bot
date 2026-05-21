from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.db.models import PlatformString, TenantLanguage, TenantStringOverride


async def load_platform_strings(session: AsyncSession, lang: str) -> dict[str, str]:
    """Return {key: text} for all PlatformString rows with the given lang."""
    result = await session.execute(
        select(PlatformString).where(PlatformString.lang == lang)
    )
    return {row.key: row.text for row in result.scalars()}


async def load_tenant_overrides(
    session: AsyncSession, tenant_id: int, lang: str
) -> dict[str, str]:
    """Return {key: text} for TenantStringOverride rows for (tenant_id, lang)."""
    result = await session.execute(
        select(TenantStringOverride).where(
            TenantStringOverride.tenant_id == tenant_id,
            TenantStringOverride.lang == lang,
        )
    )
    return {row.key: row.text for row in result.scalars()}


async def merged_strings(
    session: AsyncSession, tenant_id: int, lang: str
) -> dict[str, str]:
    """Platform strings for lang, overlaid with tenant overrides (override wins)."""
    base = await load_platform_strings(session, lang)
    overrides = await load_tenant_overrides(session, tenant_id, lang)
    return {**base, **overrides}


async def get_tenant_default_lang(session: AsyncSession, tenant_id: int) -> str | None:
    """Return the lang of the TenantLanguage row where is_default is True, or None."""
    result = await session.execute(
        select(TenantLanguage).where(
            TenantLanguage.tenant_id == tenant_id,
            TenantLanguage.is_default == True,  # noqa: E712
        )
    )
    row = result.scalars().first()
    return row.lang if row is not None else None


async def get_enabled_langs(session: AsyncSession, tenant_id: int) -> set[str]:
    """Return set of lang for TenantLanguage rows where enabled is True."""
    result = await session.execute(
        select(TenantLanguage).where(
            TenantLanguage.tenant_id == tenant_id,
            TenantLanguage.enabled == True,  # noqa: E712
        )
    )
    return {row.lang for row in result.scalars()}
