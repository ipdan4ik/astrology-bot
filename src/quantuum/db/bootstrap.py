from sqlmodel import select

from quantuum.common.crypto import encrypt_token
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountIdentity, Tenant, TenantBot
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


async def ensure_platform_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(
        select(Tenant).where(Tenant.slug == settings.platform_tenant_slug)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            slug=settings.platform_tenant_slug,
            display_name=settings.platform_tenant_name,
            is_platform=True,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant


async def ensure_master_bot(session) -> None:
    """Migrate env MASTER_BOT_TOKEN into the platform tenant's tenant_bots row (idempotent)."""
    settings = get_settings()
    token = settings.master_bot_token
    if not token:
        return
    bot_id = int(token.split(":")[0])
    existing = await session.execute(
        select(TenantBot).where(TenantBot.bot_telegram_id == bot_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    platform = await ensure_platform_tenant(session)
    session.add(
        TenantBot(
            tenant_id=platform.id,
            bot_telegram_id=bot_id,
            bot_username=settings.master_bot_username or None,
            bot_token_enc=encrypt_token(token),
            transport=settings.default_bot_transport,
            webhook_secret_path=f"master-{bot_id}",
        )
    )
    await session.commit()


async def ensure_superadmin(session) -> None:
    """Create the bootstrap superadmin account from env (idempotent, env-gated)."""
    settings = get_settings()
    email = settings.bootstrap_superadmin_email
    if not email:
        return
    existing = await session.execute(
        select(AccountIdentity).where(
            AccountIdentity.provider == "magic_link", AccountIdentity.email == email
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    account = Account(tenant_id=None, is_superadmin=True)
    session.add(account)
    await session.flush()
    session.add(
        AccountIdentity(
            account_id=account.id, provider="magic_link", email=email, verified_at=utcnow()
        )
    )
    await session.commit()
