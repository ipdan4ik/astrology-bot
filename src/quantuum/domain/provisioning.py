import asyncio

from aiogram import Bot
from aiogram.utils.token import TokenValidationError, validate_token
from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.crypto import encrypt_token
from quantuum.common.datetime import utcnow
from quantuum.common.ids import url_safe_token
from quantuum.db.models import Tenant, TenantBot, TenantInvite
from quantuum.domain.tenants import grant_role

GETME_TIMEOUT_S = 10.0


async def master_can_manage_bots(bot) -> bool:
    """True if the master bot may create managed bots programmatically (Bot API 9.6).

    Requires "Bot Management Mode" enabled on the master bot via the BotFather
    mini-app, which sets User.can_manage_bots (returned by getMe). When True,
    onboarding can mint a bot via the request_managed_bot button + getManagedBotToken
    instead of asking the owner to paste a BotFather token.
    """
    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=GETME_TIMEOUT_S)
    except (asyncio.TimeoutError, Exception):
        return False
    return bool(getattr(me, "can_manage_bots", False))


async def create_tenant_from_onboarding(
    session,
    *,
    invite: TenantInvite,
    slug: str,
    display_name: str,
    default_lang: str,
    owner_tg_id: int | str,
    owner_chat_id: int | str,
    transport: str = "polling",
) -> Tenant:
    """Atomically create a provisioning tenant + bot row and consume one invite use."""
    tenant = Tenant(
        slug=slug,
        display_name=display_name,
        tier=invite.tier,
        status="provisioning",
        owner_tg_id=str(owner_tg_id),
        owner_chat_id=str(owner_chat_id),
    )
    session.add(tenant)
    await session.flush()
    session.add(
        TenantBot(
            tenant_id=tenant.id,
            bot_token_enc=b"",
            transport=transport,
            webhook_secret_path=url_safe_token(16),
            status="provisioning",
        )
    )
    invite.used_count += 1
    if invite.used_count >= invite.max_uses:
        invite.status = "used"
        invite.used_at = utcnow()
    session.add(invite)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def validate_bot_token(token: str) -> tuple[int, str] | None:
    """Validate a Telegram bot token via get_me(). Returns (bot_id, username) or None."""
    try:
        validate_token(token)
    except TokenValidationError:
        return None
    bot = Bot(token=token)
    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=GETME_TIMEOUT_S)
        return me.id, me.username
    except Exception:
        return None
    finally:
        await bot.session.close()


async def seed_tenant_defaults(session, *, tenant_id: int, default_lang: str) -> None:
    """Seed the new tenant's languages so its bot serves the owner-chosen default lang
    (plus all other platform languages as extras). Without this the tenant has no
    language config and i18n silently falls back to English."""
    from quantuum.db.bootstrap import ensure_tenant_default_language

    await ensure_tenant_default_language(session, tenant_id, default_lang=default_lang)


async def finalize_provisioning(
    session,
    *,
    tenant_id: int,
    token: str,
    bot_telegram_id: int,
    bot_username: str | None,
    default_lang: str,
) -> TenantBot:
    """Activate a provisioning tenant: save the validated token, create the owner
    account in the new tenant, grant the owner role, and flip statuses to active."""
    tenant = await session.get(Tenant, tenant_id)
    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant_id))
    tenant_bot = result.scalars().first()

    owner_account = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=str(tenant.owner_tg_id)
    )
    await grant_role(session, tenant_id=tenant_id, account_id=owner_account.id, role="owner")

    tenant_bot.bot_token_enc = encrypt_token(token)
    tenant_bot.bot_telegram_id = bot_telegram_id
    tenant_bot.bot_username = bot_username
    tenant_bot.status = "active"
    tenant_bot.updated_at = utcnow()
    tenant.primary_owner_account_id = owner_account.id
    tenant.status = "active"
    session.add(tenant_bot)
    session.add(tenant)
    await seed_tenant_defaults(session, tenant_id=tenant_id, default_lang=default_lang)
    await session.commit()
    await session.refresh(tenant_bot)
    return tenant_bot
