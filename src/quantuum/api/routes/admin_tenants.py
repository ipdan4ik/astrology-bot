"""Tenant admin routes: GET /admin/tenants/{tenant_id}, PATCH, pause, resume,
roles CRUD, ownership transfer, i18n/config admin (Plan 5b Tasks 7-9),
tenant plans CRUD + accounts list/balance (Tasks 10-11)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_tenant_role
from quantuum.api.schemas import (
    AccountSummaryOut,
    AuditEntryOut,
    BalancePatchIn,
    ConfigPutIn,
    LanguageOut,
    LanguagesPutIn,
    PackagePlanAdminOut,
    PackagePlanCreateIn,
    PackagePlanPatchIn,
    RoleIn,
    RoleOut,
    StringOut,
    StringOverrideIn,
    SubscriptionPlanAdminOut,
    SubscriptionPlanCreateIn,
    SubscriptionPlanPatchIn,
    TenantBotBrief,
    TenantDetailOut,
    TenantPatchIn,
    TenantPlansOut,
    TenantStatsOut,
    TransferIn,
)
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    PackagePlan,
    SubscriptionPlan,
    Tenant,
    TenantBot,
    TenantConfig,
    TenantLanguage,
    TenantRole,
    TenantStringOverride,
)
from quantuum.domain.audit import list_audit, record_audit
from quantuum.domain.stats import tenant_stats
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


# ---------------------------------------------------------------------------
# Task 10 — Tenant plans CRUD (owner + admin)
# ---------------------------------------------------------------------------


def _sub_admin_out(p: SubscriptionPlan) -> SubscriptionPlanAdminOut:
    return SubscriptionPlanAdminOut(
        id=p.id, slug=p.slug, name=p.name, period_days=p.period_days,
        price_cents=p.price_cents, currency=p.currency, active=p.active,
        tenant_id=p.tenant_id,
    )


def _pkg_admin_out(p: PackagePlan) -> PackagePlanAdminOut:
    return PackagePlanAdminOut(
        id=p.id, slug=p.slug, name=p.name, request_count=p.request_count,
        price_cents=p.price_cents, currency=p.currency,
        expires_after_days=p.expires_after_days, active=p.active,
        tenant_id=p.tenant_id,
    )


@router.get("/{tenant_id}/plans", response_model=TenantPlansOut)
async def get_tenant_plans(
    tenant_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantPlansOut:
    subs_result = await session.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.tenant_id == tenant_id)
        .order_by(SubscriptionPlan.id)
    )
    pkgs_result = await session.execute(
        select(PackagePlan)
        .where(PackagePlan.tenant_id == tenant_id)
        .order_by(PackagePlan.id)
    )
    return TenantPlansOut(
        subscriptions=[_sub_admin_out(p) for p in subs_result.scalars().all()],
        packages=[_pkg_admin_out(p) for p in pkgs_result.scalars().all()],
    )


@router.post(
    "/{tenant_id}/plans/subscription",
    response_model=SubscriptionPlanAdminOut,
    status_code=201,
)
async def create_tenant_subscription_plan(
    tenant_id: int,
    body: SubscriptionPlanCreateIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionPlanAdminOut:
    plan = SubscriptionPlan(
        tenant_id=tenant_id, slug=body.slug, name=body.name,
        period_days=body.period_days, price_cents=body.price_cents,
        currency=body.currency,
    )
    session.add(plan)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="plan.create",
        entity_type="subscription_plan",
        entity_id=plan.id,
        payload={"slug": plan.slug},
    )

    await session.commit()
    await session.refresh(plan)
    return _sub_admin_out(plan)


@router.post(
    "/{tenant_id}/plans/package",
    response_model=PackagePlanAdminOut,
    status_code=201,
)
async def create_tenant_package_plan(
    tenant_id: int,
    body: PackagePlanCreateIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> PackagePlanAdminOut:
    plan = PackagePlan(
        tenant_id=tenant_id, slug=body.slug, name=body.name,
        request_count=body.request_count, price_cents=body.price_cents,
        currency=body.currency, expires_after_days=body.expires_after_days,
    )
    session.add(plan)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="plan.create",
        entity_type="package_plan",
        entity_id=plan.id,
        payload={"slug": plan.slug},
    )

    await session.commit()
    await session.refresh(plan)
    return _pkg_admin_out(plan)


@router.patch(
    "/{tenant_id}/plans/subscription/{plan_id}",
    response_model=SubscriptionPlanAdminOut,
)
async def patch_tenant_subscription_plan(
    tenant_id: int,
    plan_id: int,
    body: SubscriptionPlanPatchIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionPlanAdminOut:
    plan = await session.get(SubscriptionPlan, plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="plan not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    session.add(plan)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="plan.update",
        entity_type="subscription_plan",
        entity_id=plan_id,
        payload=body.model_dump(exclude_unset=True),
    )

    await session.commit()
    await session.refresh(plan)
    return _sub_admin_out(plan)


@router.patch(
    "/{tenant_id}/plans/package/{plan_id}",
    response_model=PackagePlanAdminOut,
)
async def patch_tenant_package_plan(
    tenant_id: int,
    plan_id: int,
    body: PackagePlanPatchIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> PackagePlanAdminOut:
    plan = await session.get(PackagePlan, plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="plan not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    session.add(plan)
    await session.flush()

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="plan.update",
        entity_type="package_plan",
        entity_id=plan_id,
        payload=body.model_dump(exclude_unset=True),
    )

    await session.commit()
    await session.refresh(plan)
    return _pkg_admin_out(plan)


# ---------------------------------------------------------------------------
# Task 11 — Accounts list + balance (owner + admin)
# ---------------------------------------------------------------------------


def _account_summary_out(
    acc: Account, bal: AccountBalance | None
) -> AccountSummaryOut:
    return AccountSummaryOut(
        id=acc.id,
        created_at=acc.created_at,
        last_seen_at=acc.last_seen_at,
        package_credits=bal.package_credits if bal is not None else 0,
        subscription_active_until=(
            bal.subscription_active_until if bal is not None else None
        ),
    )


@router.get("/{tenant_id}/accounts", response_model=list[AccountSummaryOut])
async def list_tenant_accounts(
    tenant_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> list[AccountSummaryOut]:
    result = await session.execute(
        select(Account, AccountBalance)
        .outerjoin(AccountBalance, AccountBalance.account_id == Account.id)
        .where(Account.tenant_id == tenant_id)
        .order_by(Account.id)
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()
    return [_account_summary_out(acc, bal) for acc, bal in rows]


@router.patch(
    "/{tenant_id}/accounts/{account_id}/balance",
    response_model=AccountSummaryOut,
)
async def patch_account_balance(
    tenant_id: int,
    account_id: int,
    body: BalancePatchIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> AccountSummaryOut:
    target = await session.get(Account, account_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="account not found")

    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
        session.add(bal)
        await session.flush()

    before = {
        "package_credits": bal.package_credits,
        "subscription_active_until": (
            bal.subscription_active_until.isoformat()
            if bal.subscription_active_until is not None
            else None
        ),
    }

    if body.package_credits is not None:
        bal.package_credits = body.package_credits
    if body.subscription_active_until is not None:
        bal.subscription_active_until = body.subscription_active_until
    bal.updated_at = utcnow()
    session.add(bal)
    await session.flush()

    after = {
        "package_credits": bal.package_credits,
        "subscription_active_until": (
            bal.subscription_active_until.isoformat()
            if bal.subscription_active_until is not None
            else None
        ),
    }

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="account.balance_adjust",
        entity_type="account_balance",
        entity_id=account_id,
        payload={"before": before, "after": after},
    )

    await session.commit()
    await session.refresh(target)
    await session.refresh(bal)
    return _account_summary_out(target, bal)


# ---------------------------------------------------------------------------
# Task 12 — Per-tenant real-time stats (owner + admin, read-only)
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/stats", response_model=TenantStatsOut)
async def get_tenant_stats(
    tenant_id: int,
    period_days: int = Query(default=30, ge=1, le=365),
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantStatsOut:
    stats = await tenant_stats(session, tenant_id, period_days=period_days)
    return TenantStatsOut(**stats)


# ---------------------------------------------------------------------------
# Task 15 — Tenant-scoped audit-log read (owner + admin)
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/audit-log", response_model=list[AuditEntryOut])
async def get_tenant_audit_log(
    tenant_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> list[AuditEntryOut]:
    entries = await list_audit(
        session, tenant_id=tenant_id, limit=limit, offset=offset
    )
    return [
        AuditEntryOut(
            id=e.id,
            tenant_id=e.tenant_id,
            actor_account_id=e.actor_account_id,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            created_at=e.created_at,
        )
        for e in entries
    ]
