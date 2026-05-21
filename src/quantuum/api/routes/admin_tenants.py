"""Tenant admin routes: GET /admin/tenants/{tenant_id}, PATCH, pause, resume."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_tenant_role
from quantuum.api.schemas import TenantBotBrief, TenantDetailOut, TenantPatchIn
from quantuum.db.models import Account, Tenant, TenantBot
from quantuum.domain.audit import record_audit
from quantuum.domain.tenants import set_tenant_status

router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])


def _tenant_detail_out(tenant: Tenant, bot: TenantBot | None) -> TenantDetailOut:
    return TenantDetailOut(
        id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        status=tenant.status,
        tier=tenant.tier,
        is_platform=tenant.is_platform,
        primary_owner_account_id=tenant.primary_owner_account_id,
        created_at=tenant.created_at.isoformat(),
        bot=(
            TenantBotBrief(username=bot.bot_username, status=bot.status)
            if bot is not None
            else None
        ),
    )


async def _load_tenant_and_bot(
    session: AsyncSession, tenant_id: int
) -> tuple[Tenant, TenantBot | None]:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id).limit(1)
    )
    bot = result.scalar_one_or_none()
    return tenant, bot


# ---------------------------------------------------------------------------
# GET /{tenant_id}
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}", response_model=TenantDetailOut)
async def get_tenant(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantDetailOut:
    tenant, bot = await _load_tenant_and_bot(session, tenant_id)
    return _tenant_detail_out(tenant, bot)


# ---------------------------------------------------------------------------
# PATCH /{tenant_id}
# ---------------------------------------------------------------------------


@router.patch("/{tenant_id}", response_model=TenantDetailOut)
async def patch_tenant(
    tenant_id: int,
    body: TenantPatchIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantDetailOut:
    tenant, bot = await _load_tenant_and_bot(session, tenant_id)

    before = {
        "display_name": tenant.display_name,
        "tier": tenant.tier,
    }

    if body.display_name is not None:
        tenant.display_name = body.display_name

    if body.tier is not None and account.is_superadmin:
        tenant.tier = body.tier

    after = {
        "display_name": tenant.display_name,
        "tier": tenant.tier,
    }

    session.add(tenant)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="tenant.update",
        entity_type="tenant",
        entity_id=tenant_id,
        payload={"before": before, "after": after},
    )

    await session.commit()
    await session.refresh(tenant)
    if bot is not None:
        await session.refresh(bot)
    return _tenant_detail_out(tenant, bot)


# ---------------------------------------------------------------------------
# POST /{tenant_id}/pause
# ---------------------------------------------------------------------------


@router.post("/{tenant_id}/pause", response_model=TenantDetailOut)
async def pause_tenant(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantDetailOut:
    tenant, bot = await _load_tenant_and_bot(session, tenant_id)

    if tenant.is_platform:
        raise HTTPException(status_code=400, detail="cannot pause the platform tenant")

    await set_tenant_status(session, tenant_id, status="suspended", bot_status="paused")

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="tenant.pause",
        entity_type="tenant",
        entity_id=tenant_id,
        payload={},
    )

    await session.commit()
    await session.refresh(tenant)
    if bot is not None:
        await session.refresh(bot)
    return _tenant_detail_out(tenant, bot)


# ---------------------------------------------------------------------------
# POST /{tenant_id}/resume
# ---------------------------------------------------------------------------


@router.post("/{tenant_id}/resume", response_model=TenantDetailOut)
async def resume_tenant(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantDetailOut:
    tenant, bot = await _load_tenant_and_bot(session, tenant_id)

    await set_tenant_status(session, tenant_id, status="active", bot_status="active")

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="tenant.resume",
        entity_type="tenant",
        entity_id=tenant_id,
        payload={},
    )

    await session.commit()
    await session.refresh(tenant)
    if bot is not None:
        await session.refresh(bot)
    return _tenant_detail_out(tenant, bot)
