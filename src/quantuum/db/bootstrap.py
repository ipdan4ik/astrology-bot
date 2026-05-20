from sqlmodel import select

from quantuum.common.crypto import encrypt_token
from quantuum.db.models import Tenant, TenantBot
from quantuum.domain.tenants import get_default_tenant_id
from quantuum.settings import get_settings


async def ensure_default_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=settings.default_tenant_slug, display_name=settings.default_tenant_name)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant


async def ensure_default_tenant_bot(session) -> None:
    """Migrate the env BOT_TOKEN into a tenant_bots row for the default tenant (idempotent)."""
    settings = get_settings()
    token = settings.bot_token
    if not token:
        return
    bot_id = int(token.split(":")[0])
    existing = await session.execute(
        select(TenantBot).where(TenantBot.bot_telegram_id == bot_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    tenant_id = await get_default_tenant_id(session)
    session.add(
        TenantBot(
            tenant_id=tenant_id,
            bot_telegram_id=bot_id,
            bot_token_enc=encrypt_token(token),
            transport=settings.default_bot_transport,
            webhook_secret_path=settings.webhook_secret_path or f"tg-{bot_id}",
        )
    )
    await session.commit()
