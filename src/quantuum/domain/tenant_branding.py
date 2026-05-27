from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import Tenant, TenantStringOverride

BRANDING_I18N_KEYS: tuple[str, ...] = (
    "start.welcome",
    "help.text",
    "brand.signature",
)

MAX_DISPLAY_NAME_LEN = 64
MAX_WELCOME_LEN = 2000
MAX_HELP_LEN = 2000
MAX_SIGNATURE_LEN = 200

_LIMIT_BY_KEY: dict[str, int] = {
    "start.welcome": MAX_WELCOME_LEN,
    "help.text": MAX_HELP_LEN,
    "brand.signature": MAX_SIGNATURE_LEN,
}


def _require_known_key(key: str) -> None:
    if key not in BRANDING_I18N_KEYS:
        raise ValueError(f"unknown branding key: {key}")


async def get_branding_text(
    session: AsyncSession, *, tenant_id: int, key: str, lang: str
) -> str | None:
    """Return tenant override text for (key, lang), or None when absent."""
    _require_known_key(key)
    row = await session.get(TenantStringOverride, (tenant_id, key, lang))
    return row.text if row is not None else None


async def set_branding_text(
    session: AsyncSession,
    *,
    tenant_id: int,
    key: str,
    lang: str,
    text: str,
    by_account_id: int,
) -> None:
    """Upsert TenantStringOverride for (tenant, key, lang)."""
    _require_known_key(key)
    if text == "":
        raise ValueError("empty text not allowed; use reset_branding_text to clear")
    limit = _LIMIT_BY_KEY[key]
    if len(text) > limit:
        raise ValueError(f"text too long: {len(text)} > {limit}")
    row = await session.get(TenantStringOverride, (tenant_id, key, lang))
    if row is None:
        session.add(
            TenantStringOverride(
                tenant_id=tenant_id,
                key=key,
                lang=lang,
                text=text,
                updated_by_account_id=by_account_id,
            )
        )
    else:
        row.text = text
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()


async def reset_branding_text(
    session: AsyncSession, *, tenant_id: int, key: str, lang: str
) -> None:
    """Delete tenant override row. No-op when row absent."""
    _require_known_key(key)
    await session.execute(
        delete(TenantStringOverride).where(
            TenantStringOverride.tenant_id == tenant_id,
            TenantStringOverride.key == key,
            TenantStringOverride.lang == lang,
        )
    )
    await session.flush()


async def set_display_name(
    session: AsyncSession,
    *,
    tenant_id: int,
    display_name: str,
    by_account_id: int,
) -> None:
    """Update Tenant.display_name. Validates length and disallows newlines.

    by_account_id is accepted for symmetry; audit is the caller's responsibility.
    """
    if display_name == "":
        raise ValueError("empty display_name not allowed")
    if len(display_name) > MAX_DISPLAY_NAME_LEN:
        raise ValueError(
            f"display_name too long: {len(display_name)} > {MAX_DISPLAY_NAME_LEN}"
        )
    if "\n" in display_name or "\r" in display_name:
        raise ValueError("display_name must not contain newlines")
    row = await session.get(Tenant, tenant_id)
    if row is None:
        raise ValueError(f"tenant {tenant_id} not found")
    row.display_name = display_name
    await session.flush()
