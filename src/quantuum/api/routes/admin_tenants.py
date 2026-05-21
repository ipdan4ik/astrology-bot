"""Tenant admin routes: GET /admin/tenants/{tenant_id}, PATCH, pause, resume,
roles CRUD, ownership transfer, and i18n/config admin (Plan 5b Tasks 7-9)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_tenant_role
from quantuum.api.schemas import (
    ConfigPutIn,
    LanguageOut,
    LanguagesPutIn,
    RoleIn,
    RoleOut,
    StringOut,
    StringOverrideIn,
    TenantBotBrief,
    TenantDetailOut,
    TenantPatchIn,
    TransferIn,
)
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    Tenant,
    TenantBot,
    TenantConfig,
    TenantLanguage,
    TenantRole,
    TenantStringOverride,
)
from quantuum.domain.audit import record_audit
from quantuum.domain.tenants import (
    account_has_role,
    count_owners,
    list_roles,
    revoke_role,
    set_tenant_status,
    transfer_ownership,
)
from quantuum.i18n.cache import invalidate_i18n
from quantuum.i18n.strings import load_platform_strings, load_tenant_overrides

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


# ---------------------------------------------------------------------------
# Task 7 — Languages
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/languages", response_model=list[LanguageOut])
async def get_tenant_languages(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> list[LanguageOut]:
    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows = result.scalars().all()
    return [LanguageOut(lang=r.lang, enabled=r.enabled, is_default=r.is_default) for r in rows]


@router.put("/{tenant_id}/languages", response_model=list[LanguageOut])
async def put_tenant_languages(
    tenant_id: int,
    body: LanguagesPutIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> list[LanguageOut]:
    # Validate exactly one default
    defaults = [item for item in body.languages if item.is_default]
    if len(defaults) != 1:
        raise HTTPException(
            status_code=400,
            detail="exactly one language must have is_default=true",
        )

    # Step 1: clear all existing is_default flags for this tenant to avoid the
    # partial unique index violation when switching the default row.
    existing_result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    existing_rows: dict[str, TenantLanguage] = {
        r.lang: r for r in existing_result.scalars()
    }

    for row in existing_rows.values():
        if row.is_default:
            row.is_default = False
            session.add(row)
    await session.flush()

    # Step 2: upsert each item
    for item in body.languages:
        if item.lang in existing_rows:
            row = existing_rows[item.lang]
            row.enabled = item.enabled
            row.is_default = item.is_default
            session.add(row)
        else:
            new_row = TenantLanguage(
                tenant_id=tenant_id,
                lang=item.lang,
                enabled=item.enabled,
                is_default=item.is_default,
            )
            session.add(new_row)

    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="languages.update",
        entity_type="tenant",
        entity_id=tenant_id,
        payload={"languages": [i.model_dump() for i in body.languages]},
    )

    await session.commit()

    await invalidate_i18n(tenant_id)

    # Re-fetch and return
    refreshed = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows = refreshed.scalars().all()
    return [LanguageOut(lang=r.lang, enabled=r.enabled, is_default=r.is_default) for r in rows]


# ---------------------------------------------------------------------------
# Task 8 — String overrides
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/strings", response_model=list[StringOut])
async def get_tenant_strings(
    tenant_id: int,
    lang: str,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> list[StringOut]:
    platform = await load_platform_strings(session, lang)
    overrides = await load_tenant_overrides(session, tenant_id, lang)
    out: list[StringOut] = []
    for key, platform_text in platform.items():
        if key in overrides:
            out.append(StringOut(key=key, lang=lang, text=overrides[key], is_override=True))
        else:
            out.append(StringOut(key=key, lang=lang, text=platform_text, is_override=False))
    return out


@router.put("/{tenant_id}/strings", response_model=StringOut)
async def put_tenant_string_override(
    tenant_id: int,
    body: StringOverrideIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> StringOut:
    # Upsert TenantStringOverride
    existing = await session.get(
        TenantStringOverride, (tenant_id, body.key, body.lang)
    )
    if existing is not None:
        existing.text = body.text
        existing.updated_at = utcnow()
        existing.updated_by_account_id = account.id
        session.add(existing)
    else:
        row = TenantStringOverride(
            tenant_id=tenant_id,
            key=body.key,
            lang=body.lang,
            text=body.text,
            updated_at=utcnow(),
            updated_by_account_id=account.id,
        )
        session.add(row)

    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="string.override",
        entity_type="tenant_string_override",
        entity_id=f"{body.key}:{body.lang}",
        payload={"key": body.key, "lang": body.lang},
    )

    await session.commit()

    await invalidate_i18n(tenant_id, body.lang)

    return StringOut(key=body.key, lang=body.lang, text=body.text, is_override=True)


@router.delete("/{tenant_id}/strings/{key}/{lang}", status_code=200)
async def delete_tenant_string_override(
    tenant_id: int,
    key: str,
    lang: str,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(TenantStringOverride, (tenant_id, key, lang))
    if row is None:
        raise HTTPException(status_code=404, detail="string override not found")

    await session.delete(row)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="string.revert",
        entity_type="tenant_string_override",
        entity_id=f"{key}:{lang}",
        payload={"key": key, "lang": lang},
    )

    await session.commit()

    await invalidate_i18n(tenant_id, lang)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Task 9 — Config
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/config")
async def get_tenant_config(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )
    rows = result.scalars().all()
    return {row.key: row.value_jsonb for row in rows}


@router.put("/{tenant_id}/config")
async def put_tenant_config(
    tenant_id: int,
    body: ConfigPutIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> dict:
    existing = await session.get(TenantConfig, (tenant_id, body.key))
    if existing is not None:
        existing.value_jsonb = body.value
        existing.updated_at = utcnow()
        existing.updated_by_account_id = account.id
        session.add(existing)
    else:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=body.key,
            value_jsonb=body.value,
            updated_at=utcnow(),
            updated_by_account_id=account.id,
        )
        session.add(row)

    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="config.update",
        entity_type="tenant_config",
        entity_id=body.key,
        payload={"key": body.key},
    )

    await session.commit()

    return {"key": body.key, "value": body.value}
