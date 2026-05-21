from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_superadmin
from quantuum.api.schemas import (
    InviteCreateIn,
    InviteOut,
    PlatformStatsOut,
    TenantOut,
)
from quantuum.db.models import Account, Tenant, TenantInvite
from quantuum.domain.invites import create_invite, list_invites, revoke_invite
from quantuum.domain.stats import platform_stats
from quantuum.settings import get_settings

router = APIRouter(prefix="/admin/platform", tags=["admin-platform"])


def _invite_out(invite: TenantInvite) -> InviteOut:
    username = get_settings().master_bot_username
    deeplink = f"https://t.me/{username}?start={invite.code}"
    return InviteOut(
        id=invite.id,
        code=invite.code,
        tier=invite.tier,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        status=invite.status,
        deeplink=deeplink,
    )


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite_route(
    body: InviteCreateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    invite = await create_invite(
        session,
        created_by_account_id=admin.id,
        tier=body.tier,
        max_uses=body.max_uses,
        expires_at=body.expires_at,
        preset_slug=body.preset_slug,
        preset_display_name=body.preset_display_name,
        preset_username=body.preset_username,
        preset_default_lang=body.preset_default_lang,
    )
    return _invite_out(invite)


@router.get("/invites", response_model=list[InviteOut])
async def list_invites_route(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[InviteOut]:
    return [_invite_out(i) for i in await list_invites(session)]


@router.post("/invites/{invite_id}/revoke", response_model=InviteOut)
async def revoke_invite_route(
    invite_id: int,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    invite = await revoke_invite(session, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="invite not found")
    return _invite_out(invite)


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants_route(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[TenantOut]:
    result = await session.execute(select(Tenant).order_by(Tenant.id))
    return [
        TenantOut(
            id=t.id,
            slug=t.slug,
            display_name=t.display_name,
            tier=t.tier,
            status=t.status,
            is_platform=t.is_platform,
        )
        for t in result.scalars().all()
    ]


@router.get("/stats", response_model=PlatformStatsOut)
async def get_platform_stats(
    period_days: int = Query(default=30, ge=1, le=365),
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PlatformStatsOut:
    stats = await platform_stats(session, period_days=period_days)
    return PlatformStatsOut(**stats)
