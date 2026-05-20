from quantuum.common.datetime import utcnow
from quantuum.common.ids import url_safe_token
from quantuum.db.models import Tenant, TenantBot, TenantInvite


async def try_programmatic_create(*, slug: str, display_name: str) -> str | None:
    """MVP: Telegram has no official API to create bots programmatically.

    Always returns None so provisioning takes the BotFather-fallback path
    (owner pastes a token into the master bot). This is the seam where a future
    programmatic-creation integration would return a freshly minted token.
    """
    return None


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
