from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_superadmin
from quantuum.api.schemas import (
    AuditEntryOut,
    InviteCreateIn,
    InviteOut,
    LLMConfigOut,
    LLMConfigPutIn,
    PlatformConfigPutIn,
    PlatformStatsOut,
    PlatformStringIn,
    PlatformStringOut,
    SuperadminIn,
    SuperadminOut,
    TenantOut,
)
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountIdentity,
    PlatformConfig,
    PlatformString,
    Tenant,
    TenantInvite,
)
from quantuum.domain.audit import list_audit, record_audit
from quantuum.domain.invites import create_invite, list_invites, revoke_invite
from quantuum.domain.llm_config import get_llm_config, set_llm_config
from quantuum.domain.stats import platform_stats
from quantuum.i18n.cache import invalidate_i18n_all
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
    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.invite.create",
        entity_type="tenant_invite",
        entity_id=invite.id,
        payload={"tier": invite.tier, "max_uses": invite.max_uses},
    )
    await session.commit()
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
    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.invite.revoke",
        entity_type="tenant_invite",
        entity_id=invite.id,
    )
    await session.commit()
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


# ---------------------------------------------------------------------------
# Task 14 — Platform config
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_platform_config(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(PlatformConfig))
    return {row.key: row.value_jsonb for row in result.scalars()}


@router.put("/config")
async def put_platform_config(
    body: PlatformConfigPutIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    existing = await session.get(PlatformConfig, body.key)
    if existing is not None:
        existing.value_jsonb = body.value
        existing.updated_at = utcnow()
        existing.updated_by_account_id = admin.id
        session.add(existing)
    else:
        session.add(
            PlatformConfig(
                key=body.key,
                value_jsonb=body.value,
                updated_at=utcnow(),
                updated_by_account_id=admin.id,
            )
        )

    await session.flush()

    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.config.update",
        entity_type="platform_config",
        entity_id=body.key,
        payload={"key": body.key},
    )

    await session.commit()
    return {"key": body.key, "value": body.value}


# ---------------------------------------------------------------------------
# Task 6 (Plan 5d) — LLM config (DB-backed, env key stays env-only)
# ---------------------------------------------------------------------------


def _llm_config_out(cfg: dict) -> LLMConfigOut:
    return LLMConfigOut(
        provider=cfg["provider"],
        model=cfg["model"],
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
        api_key_configured=bool(get_settings().llm_api_key),
    )


@router.get("/llm", response_model=LLMConfigOut)
async def get_llm_config_route(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> LLMConfigOut:
    cfg = await get_llm_config(session)
    return _llm_config_out(cfg)


@router.put("/llm", response_model=LLMConfigOut)
async def put_llm_config_route(
    body: LLMConfigPutIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> LLMConfigOut:
    provided = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = await set_llm_config(session, actor_id=admin.id, **provided)
    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.llm.update",
        entity_type="platform_config",
        payload=provided,
    )
    await session.commit()
    return _llm_config_out(cfg)


# ---------------------------------------------------------------------------
# Task 14 — Platform strings
# ---------------------------------------------------------------------------


@router.get("/strings", response_model=list[PlatformStringOut])
async def get_platform_strings(
    lang: str,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[PlatformStringOut]:
    result = await session.execute(
        select(PlatformString).where(PlatformString.lang == lang)
    )
    return [
        PlatformStringOut(key=row.key, lang=row.lang, text=row.text)
        for row in result.scalars()
    ]


@router.put("/strings", response_model=PlatformStringOut)
async def put_platform_string(
    body: PlatformStringIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PlatformStringOut:
    existing = await session.get(PlatformString, (body.key, body.lang))
    if existing is not None:
        existing.text = body.text
        session.add(existing)
    else:
        session.add(
            PlatformString(key=body.key, lang=body.lang, text=body.text)
        )

    await session.flush()

    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.string.update",
        entity_type="platform_string",
        entity_id=f"{body.key}:{body.lang}",
        payload={"key": body.key, "lang": body.lang},
    )

    await session.commit()

    # Platform strings affect every tenant — clear all tenants' caches for lang.
    await invalidate_i18n_all(body.lang)

    return PlatformStringOut(key=body.key, lang=body.lang, text=body.text)


# ---------------------------------------------------------------------------
# Task 14 — Superadmins
# ---------------------------------------------------------------------------


@router.get("/superadmins", response_model=list[SuperadminOut])
async def list_superadmins(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[SuperadminOut]:
    result = await session.execute(
        select(Account, AccountIdentity)
        .outerjoin(
            AccountIdentity,
            (AccountIdentity.account_id == Account.id)
            & (AccountIdentity.provider == "magic_link"),
        )
        .where(Account.is_superadmin == True)  # noqa: E712
        .order_by(Account.id)
    )
    # An account may have multiple magic_link identities; first email wins.
    seen: dict[int, SuperadminOut] = {}
    for acc, identity in result.all():
        if acc.id in seen:
            if seen[acc.id].email is None and identity is not None:
                seen[acc.id].email = identity.email
            continue
        seen[acc.id] = SuperadminOut(
            account_id=acc.id,
            email=identity.email if identity is not None else None,
        )
    return list(seen.values())


@router.post("/superadmins", response_model=SuperadminOut)
async def grant_superadmin(
    body: SuperadminIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> SuperadminOut:
    target = await session.get(Account, body.account_id)
    if target is None:
        raise HTTPException(status_code=404, detail="account not found")

    target.is_superadmin = True
    session.add(target)
    await session.flush()

    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.superadmin.grant",
        entity_type="account",
        entity_id=body.account_id,
        payload={"account_id": body.account_id},
    )

    await session.commit()

    email_result = await session.execute(
        select(AccountIdentity.email)
        .where(
            AccountIdentity.account_id == body.account_id,
            AccountIdentity.provider == "magic_link",
        )
        .limit(1)
    )
    email = email_result.scalar_one_or_none()
    return SuperadminOut(account_id=body.account_id, email=email)


@router.delete("/superadmins/{account_id}", status_code=200)
async def revoke_superadmin(
    account_id: int,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    target = await session.get(Account, account_id)
    if target is None or not target.is_superadmin:
        raise HTTPException(status_code=404, detail="superadmin not found")

    count_result = await session.execute(
        select(func.count())
        .select_from(Account)
        .where(Account.is_superadmin == True)  # noqa: E712
    )
    if count_result.scalar_one() <= 1:
        raise HTTPException(
            status_code=400, detail="cannot remove the last superadmin"
        )

    target.is_superadmin = False
    session.add(target)
    await session.flush()

    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action="platform.superadmin.revoke",
        entity_type="account",
        entity_id=account_id,
        payload={"account_id": account_id},
    )

    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Task 15 — Tenant suspend / archive
# ---------------------------------------------------------------------------


async def _set_platform_tenant_status(
    session: AsyncSession,
    *,
    tenant_id: int,
    status: str,
    action: str,
    admin: Account,
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    if tenant.is_platform:
        raise HTTPException(
            status_code=400, detail="cannot change status of the platform tenant"
        )

    tenant.status = status
    session.add(tenant)
    await session.flush()

    await record_audit(
        session,
        tenant_id=None,
        actor_account_id=admin.id,
        action=action,
        entity_type="tenant",
        entity_id=tenant_id,
        payload={"status": status},
    )

    await session.commit()
    await session.refresh(tenant)
    return tenant


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantOut)
async def suspend_tenant(
    tenant_id: int,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> TenantOut:
    tenant = await _set_platform_tenant_status(
        session,
        tenant_id=tenant_id,
        status="suspended",
        action="platform.tenant.suspend",
        admin=admin,
    )
    return TenantOut(
        id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        tier=tenant.tier,
        status=tenant.status,
        is_platform=tenant.is_platform,
    )


@router.post("/tenants/{tenant_id}/archive", response_model=TenantOut)
async def archive_tenant(
    tenant_id: int,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> TenantOut:
    tenant = await _set_platform_tenant_status(
        session,
        tenant_id=tenant_id,
        status="archived",
        action="platform.tenant.archive",
        admin=admin,
    )
    return TenantOut(
        id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        tier=tenant.tier,
        status=tenant.status,
        is_platform=tenant.is_platform,
    )


# ---------------------------------------------------------------------------
# Task 15 — Platform audit-log read
# ---------------------------------------------------------------------------


def _audit_entry_out(entry) -> AuditEntryOut:
    return AuditEntryOut(
        id=entry.id,
        tenant_id=entry.tenant_id,
        actor_account_id=entry.actor_account_id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        created_at=entry.created_at,
    )


@router.get("/audit-log", response_model=list[AuditEntryOut])
async def get_platform_audit_log(
    tenant_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[AuditEntryOut]:
    entries = await list_audit(
        session, tenant_id=tenant_id, limit=limit, offset=offset
    )
    return [_audit_entry_out(e) for e in entries]
