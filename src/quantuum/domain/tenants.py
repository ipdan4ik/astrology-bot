from sqlmodel import select

from quantuum.db.models import Tenant, TenantBot, TenantRole
from quantuum.settings import get_settings


async def get_default_tenant_id(session) -> int:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one()
    return tenant.id


async def resolve_tenant_id_by_bot(session, bot_telegram_id: int) -> int | None:
    result = await session.execute(
        select(TenantBot.tenant_id).where(
            TenantBot.bot_telegram_id == bot_telegram_id, TenantBot.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_bot_by_webhook_secret(session, secret: str) -> TenantBot | None:
    result = await session.execute(
        select(TenantBot).where(
            TenantBot.webhook_secret_path == secret, TenantBot.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def list_active_tenant_bots(session, transport: str | None = None) -> list[TenantBot]:
    query = select(TenantBot).where(TenantBot.status == "active")
    if transport is not None:
        query = query.where(TenantBot.transport == transport)
    result = await session.execute(query)
    return list(result.scalars().all())


async def grant_role(
    session, *, tenant_id: int, account_id: int, role: str, granted_by_account_id: int | None = None
) -> None:
    if await account_has_role(session, tenant_id=tenant_id, account_id=account_id, role=role):
        return
    session.add(
        TenantRole(
            tenant_id=tenant_id, account_id=account_id, role=role,
            granted_by_account_id=granted_by_account_id,
        )
    )
    await session.commit()


async def account_has_role(session, *, tenant_id: int, account_id: int, role: str) -> bool:
    result = await session.execute(
        select(TenantRole.id).where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.account_id == account_id,
            TenantRole.role == role,
        )
    )
    return result.scalar_one_or_none() is not None
