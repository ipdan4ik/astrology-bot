"""Tenant admin routes: GET /admin/tenants/{tenant_id}, PATCH, pause, resume,
roles CRUD, and ownership transfer."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_tenant_role
from quantuum.api.schemas import (
    RoleIn,
    RoleOut,
    TenantBotBrief,
    TenantDetailOut,
    TenantPatchIn,
    TransferIn,
)
from quantuum.db.models import Account, Tenant, TenantBot, TenantRole
from quantuum.domain.audit import record_audit
from quantuum.domain.tenants import (
    account_has_role,
    count_owners,
    list_roles,
    revoke_role,
    set_tenant_status,
    transfer_ownership,
)

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


# ---------------------------------------------------------------------------
# GET /{tenant_id}/roles  (owner + admin)
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/roles", response_model=list[RoleOut])
async def get_tenant_roles(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> list[RoleOut]:
    roles = await list_roles(session, tenant_id)
    return [
        RoleOut(
            id=r.id,
            account_id=r.account_id,
            role=r.role,
            granted_at=r.granted_at,
        )
        for r in roles
    ]


# ---------------------------------------------------------------------------
# POST /{tenant_id}/roles  (owner-only)
# ---------------------------------------------------------------------------

_VALID_ROLES = {"owner", "admin"}


@router.post("/{tenant_id}/roles", response_model=RoleOut, status_code=201)
async def grant_tenant_role(
    tenant_id: int,
    body: RoleIn,
    account: Account = Depends(require_tenant_role(("owner",))),
    session: AsyncSession = Depends(get_session),
) -> RoleOut:
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"invalid role; must be one of {_VALID_ROLES}")

    # Target account must belong to this tenant.
    target = await session.get(Account, body.account_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="account does not belong to this tenant")

    # Duplicate check.
    if await account_has_role(
        session, tenant_id=tenant_id, account_id=body.account_id, role=body.role
    ):
        raise HTTPException(status_code=409, detail="role already exists")

    role = TenantRole(
        tenant_id=tenant_id,
        account_id=body.account_id,
        role=body.role,
        granted_by_account_id=account.id,
    )
    session.add(role)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="role.grant",
        entity_type="tenant_role",
        entity_id=role.id,
        payload={"account_id": body.account_id, "role": body.role},
    )

    await session.commit()
    await session.refresh(role)
    return RoleOut(
        id=role.id,
        account_id=role.account_id,
        role=role.role,
        granted_at=role.granted_at,
    )


# ---------------------------------------------------------------------------
# DELETE /{tenant_id}/roles/{role_id}  (owner-only)
# ---------------------------------------------------------------------------


@router.delete("/{tenant_id}/roles/{role_id}", status_code=200)
async def revoke_tenant_role(
    tenant_id: int,
    role_id: int,
    account: Account = Depends(require_tenant_role(("owner",))),
    session: AsyncSession = Depends(get_session),
) -> dict:
    role = await session.get(TenantRole, role_id)
    if role is None or role.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="role not found")

    if role.role == "owner" and await count_owners(session, tenant_id) <= 1:
        raise HTTPException(status_code=400, detail="cannot remove last owner")

    deleted = await revoke_role(session, role_id)

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="role.revoke",
        entity_type="tenant_role",
        entity_id=role_id,
        payload={"account_id": deleted.account_id if deleted else None, "role": role.role},
    )

    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /{tenant_id}/transfer  (owner-only)
# ---------------------------------------------------------------------------


@router.post("/{tenant_id}/transfer", response_model=TenantDetailOut)
async def transfer_tenant_ownership(
    tenant_id: int,
    body: TransferIn,
    account: Account = Depends(require_tenant_role(("owner",))),
    session: AsyncSession = Depends(get_session),
) -> TenantDetailOut:
    # Validate target account.
    target = await session.get(Account, body.new_owner_account_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="account does not belong to this tenant")

    tenant, bot = await _load_tenant_and_bot(session, tenant_id)
    before_primary = tenant.primary_owner_account_id

    tenant = await transfer_ownership(
        session,
        tenant_id=tenant_id,
        new_owner_account_id=body.new_owner_account_id,
        revoke_previous=body.revoke_previous,
        actor_id=account.id,
    )

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="tenant.transfer",
        entity_type="tenant",
        entity_id=tenant_id,
        payload={
            "before_primary": before_primary,
            "after_primary": body.new_owner_account_id,
            "revoke_previous": body.revoke_previous,
        },
    )

    await session.commit()
    await session.refresh(tenant)
    if bot is not None:
        await session.refresh(bot)
    return _tenant_detail_out(tenant, bot)
