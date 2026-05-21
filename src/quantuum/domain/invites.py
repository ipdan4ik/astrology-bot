from datetime import datetime

from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.ids import url_safe_token
from quantuum.db.models import TenantInvite


async def create_invite(
    session,
    *,
    created_by_account_id: int | None,
    tier: str = "basic",
    max_uses: int = 1,
    expires_at: datetime | None = None,
    preset_slug: str | None = None,
    preset_display_name: str | None = None,
    preset_username: str | None = None,
    preset_default_lang: str | None = None,
) -> TenantInvite:
    invite = TenantInvite(
        code=url_safe_token(16),
        created_by_account_id=created_by_account_id,
        tier=tier,
        max_uses=max_uses,
        expires_at=expires_at,
        preset_slug=preset_slug,
        preset_display_name=preset_display_name,
        preset_username=preset_username,
        preset_default_lang=preset_default_lang,
    )
    session.add(invite)
    await session.flush()
    await session.refresh(invite)
    return invite


async def list_invites(session) -> list[TenantInvite]:
    result = await session.execute(select(TenantInvite).order_by(TenantInvite.id.desc()))
    return list(result.scalars().all())


async def get_invite_by_code(session, code: str) -> TenantInvite | None:
    result = await session.execute(select(TenantInvite).where(TenantInvite.code == code))
    return result.scalar_one_or_none()


async def revoke_invite(session, invite_id: int) -> TenantInvite | None:
    invite = await session.get(TenantInvite, invite_id)
    if invite is None:
        return None
    invite.status = "revoked"
    session.add(invite)
    await session.flush()
    await session.refresh(invite)
    return invite


def invite_is_usable(invite, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if invite.status != "active":
        return False
    if invite.expires_at is not None and invite.expires_at < now:
        return False
    if invite.used_count >= invite.max_uses:
        return False
    return True
