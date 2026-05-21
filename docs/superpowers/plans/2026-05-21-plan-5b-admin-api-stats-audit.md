# Plan 5b — Admin & Tenant API + Stats + Audit Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Build the tenant- and platform-management API surface: a `require_tenant_role` auth dependency, an `audit_log` of mutating admin actions, tenant management (get/patch/pause/resume/transfer/roles), the tenant i18n admin surface (config/strings/languages, wired to `invalidate_i18n`), tenant plan CRUD, and real-time SQL stats (per-tenant + platform).

**Architecture:** New `audit_log` table + `domain/audit.py` helper. New `deps.require_tenant_role(...)` mirroring `require_superadmin`. New routes under `src/quantuum/api/routes/admin_tenants.py` (tenant-scoped) and additions to `admin_platform.py`. Stats are real-time SQL aggregations in `domain/stats.py`. Every mutating admin route records an audit entry.

**Tech Stack:** FastAPI, SQLModel/asyncpg/Alembic, the i18n layer from 5a (`quantuum.i18n.invalidate_i18n`, `strings.py`), pytest + httpx ASGITransport. Spec refs: §5 "Authorization helpers", §9 "Admin API & stats", §4 "Audit".

---

## Conventions (from the existing codebase)
- Auth deps live in `src/quantuum/api/deps.py`: `current_account`, `require_superadmin`. JWT issued via `quantuum.auth.jwt_tokens.issue_access_token(account_id, tenant_id, is_superadmin)`.
- Routers: `APIRouter(prefix=..., tags=[...])`, mounted in `src/quantuum/api/app.py`.
- Schemas in `src/quantuum/api/schemas.py` (Pydantic v2 BaseModel).
- API tests: `client` (ASGITransport over `create_app()`), `sa_headers` (superadmin), `customer_headers` fixtures — see `tests/test_api_admin_platform.py` for the exact pattern. Add an `owner_headers`/`admin_headers` helper as needed.
- `TenantRole(tenant_id, account_id, role)` with unique `(tenant_id, account_id, role)`; `domain/tenants.py` has `account_has_role(session, *, tenant_id, account_id, role)` and `grant_role(...)`.
- Tenant: `status active|suspended|archived`, `tier basic|vip`, `primary_owner_account_id`. TenantBot: `status active|paused|error`.

## Deferred (documented, NOT built in 5b — straightforward to add later, not needed by 5c)
- `/admin/tenants/{id}/accounts` detail + `/blueprints`,`/requests`,`/payments` read lists (per-account drill-down). 5b builds `accounts` LIST + balance PATCH only.
- `/admin/platform/llm` provider/credential management UI (providers are seeded via bootstrap in MVP).
- Materialized stats views (real-time SQL only for now, per spec §639).

---

## Phase 1 — Foundations

### Task 1: `require_tenant_role` dependency

**Files:** Modify `src/quantuum/api/deps.py`; Test `tests/test_deps_tenant_role.py`.

Add a dependency FACTORY (spec §328 `require_tenant_role(tenant_id, roles=("owner",))`). FastAPI path param `tenant_id` is in the route, so implement as a factory returning a dependency that reads the path `tenant_id` and the `current_account`:

```python
def require_tenant_role(roles: tuple[str, ...] = ("owner", "admin")):
    async def _dep(
        tenant_id: int,
        account: Account = Depends(current_account),
        session: AsyncSession = Depends(get_session),
    ) -> Account:
        if account.is_superadmin:
            return account  # superadmin has access to every tenant
        if account.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="forbidden")
        for role in roles:
            if await account_has_role(session, tenant_id=tenant_id, account_id=account.id, role=role):
                return account
        raise HTTPException(status_code=403, detail="insufficient role")
    return _dep
```
Use it as `account = Depends(require_tenant_role(("owner", "admin")))` in tenant routes. Owner-only routes pass `("owner",)`.

- [ ] Step 1: failing test — using the API test fixtures, build an owner account (tenant_role owner), an admin account, a plain customer, a superadmin, and a different-tenant account. Drive a tiny throwaway route OR test the dep via a real route added in Task 3. Simplest: write the test against the GET tenant route from Task 3 — so write Task 1's dep + a minimal probe route here, OR fold the auth assertions into Task 3's tests. RECOMMENDED: implement the dep here with a focused unit-style test that calls `_dep` directly with constructed accounts/session (superadmin passes; matching owner passes; admin passes when in roles; customer 403; wrong-tenant 403).
- [ ] Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5b): require_tenant_role dependency (tenant_roles + superadmin override)`.

### Task 2: `audit_log` model + migration + `record_audit` helper

**Files:** Modify `src/quantuum/db/models.py`; Create `alembic/versions/a6b7c8d9e0f1_audit_log.py`; Create `src/quantuum/domain/audit.py`; Test `tests/test_audit.py`.

Model (spec §257):
```python
class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),)
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)  # NULL = platform action
    actor_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    payload_jsonb: dict = Field(default_factory=dict, sa_column=Column(JSONB))  # before/after snapshot
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
```
Migration `down_revision = "f5e6a7b8c9d0"` (5a's head — confirm with `alembic heads`); create the table + index.

`domain/audit.py`:
```python
async def record_audit(session, *, tenant_id, actor_account_id, action, entity_type=None,
                       entity_id=None, payload=None, request_id=None, ip_address=None,
                       user_agent=None) -> AuditLog:
    entry = AuditLog(tenant_id=tenant_id, actor_account_id=actor_account_id, action=action,
                     entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None,
                     payload_jsonb=payload or {}, request_id=request_id, ip_address=ip_address,
                     user_agent=user_agent)
    session.add(entry)
    await session.flush()
    return entry

async def list_audit(session, *, tenant_id=None, limit=100, offset=0) -> list[AuditLog]:
    # platform view = tenant_id None filter NOT applied (all); tenant view = filter by tenant_id
    ...
```
Routes call `record_audit` within their session before commit, capturing a `{"before":..., "after":...}` payload for mutations.

- [ ] Steps: failing test (record an entry; list filters by tenant; platform list returns all) → model+migration+helper → PASS + ruff → commit `feat(5b): audit_log model + record_audit helper`.

---

## Phase 2 — Tenant management

### Task 3: GET/PATCH `/admin/tenants/{id}`

**Files:** Create `src/quantuum/api/routes/admin_tenants.py`; add schemas `TenantDetailOut`, `TenantPatchIn`; mount router in `app.py`; Test `tests/test_api_admin_tenants.py`.

- `GET /admin/tenants/{tenant_id}` (role owner/admin) → tenant detail (id, slug, display_name, status, tier, is_platform, primary_owner_account_id, created_at) + the tenant's bot summary (username/status) if present.
- `PATCH /admin/tenants/{tenant_id}` (owner/admin) → update `display_name` (and `tier` only when superadmin). Record audit `tenant.update` with before/after.

- [ ] Steps: failing tests (owner can GET/PATCH; admin can; customer 403; wrong-tenant 403; superadmin can; PATCH writes audit) → implement → PASS + ruff → commit `feat(5b): tenant GET/PATCH + audit`.

### Task 4: pause/resume `/admin/tenants/{id}/pause|resume`

**Files:** Modify `admin_tenants.py`; domain helper in `domain/tenants.py` (`set_tenant_status`, also flips its `tenant_bots.status`); Test additions.

- `POST /admin/tenants/{tenant_id}/pause` (owner/admin) → tenant.status="suspended" + its tenant_bots.status="paused"; audit `tenant.pause`.
- `POST /admin/tenants/{tenant_id}/resume` → status back to "active"/"active"; audit `tenant.resume`.
(Do not allow pausing the platform tenant — 400.)

- [ ] Steps: failing tests (pause sets statuses + audit; resume restores; platform tenant 400) → implement → PASS + ruff → commit `feat(5b): tenant pause/resume + audit`.

### Task 5: roles CRUD `/admin/tenants/{id}/roles` (owner-only)

**Files:** Modify `admin_tenants.py`; schemas `RoleIn`, `RoleOut`; domain helpers (`list_roles`, `revoke_role`); Test additions.

- `GET /admin/tenants/{tenant_id}/roles` (owner/admin) → list roles (account_id, role, granted_at).
- `POST /admin/tenants/{tenant_id}/roles` (owner-only) `{account_id, role}` → grant (reuse `grant_role`); 409 if exists; audit `role.grant`.
- `DELETE /admin/tenants/{tenant_id}/roles/{role_id}` (owner-only) → revoke; cannot revoke the last owner (400); audit `role.revoke`.

- [ ] Steps: failing tests (owner grants/revokes; admin can list but POST/DELETE 403; cannot remove last owner) → implement → PASS + ruff → commit `feat(5b): tenant roles CRUD (owner-only) + audit`.

### Task 6: transfer ownership `/admin/tenants/{id}/transfer` (owner-only)

**Files:** Modify `admin_tenants.py`; schemas `TransferIn`; domain helper `transfer_ownership(session, *, tenant_id, new_owner_account_id, actor_id)`; Test additions.

- `POST /admin/tenants/{tenant_id}/transfer` (owner-only) `{new_owner_account_id}` → atomically: grant `owner` role to the target (if not present), set `tenant.primary_owner_account_id = new_owner`, keep or revoke the prior owner per spec (MVP: keep prior owner's role unless `revoke_previous=true`). The target account must belong to the same tenant (else 400). Audit `tenant.transfer` with before/after primary_owner.

- [ ] Steps: failing tests (owner transfers → primary_owner updated + target has owner role; non-owner 403; target in another tenant 400) → implement → PASS + ruff → commit `feat(5b): tenant ownership transfer + audit`.

---

## Phase 3 — i18n admin + config + plans + accounts

### Task 7: tenant languages `/admin/tenants/{id}/languages`

**Files:** Modify `admin_tenants.py`; schemas `LanguageOut`, `LanguagesPutIn`; domain helpers in a new `domain/tenant_i18n.py` (or extend `i18n/strings.py` with write helpers); Test additions.

- `GET /admin/tenants/{tenant_id}/languages` (owner/admin) → list (lang, enabled, is_default).
- `PUT /admin/tenants/{tenant_id}/languages` (owner/admin) `{languages:[{lang,enabled,is_default}]}` → upsert the set, enforcing exactly one default (set others' is_default false in the same txn). After commit, call `invalidate_i18n(tenant_id)` (all langs). Audit `languages.update`.

- [ ] Steps: failing tests (set langs; exactly-one-default enforced; invalidate called — assert cache cleared or spy on invalidate_i18n) → implement → PASS + ruff → commit `feat(5b): tenant languages admin + i18n invalidation`.

### Task 8: tenant string overrides `/admin/tenants/{id}/strings`

**Files:** Modify `admin_tenants.py`; schemas `StringOverrideIn`, `StringOut`; Test additions.

- `GET /admin/tenants/{tenant_id}/strings?lang=` (owner/admin) → merged view: platform strings for lang with the tenant's overrides flagged (return `{key, lang, text, is_override}`), so the owner sees what they can customize.
- `PUT /admin/tenants/{tenant_id}/strings` (owner/admin) `{key, lang, text}` → upsert a `tenant_string_overrides` row (set `updated_by_account_id`); after commit `invalidate_i18n(tenant_id, lang)`. Audit `string.override`.
- `DELETE /admin/tenants/{tenant_id}/strings/{key}/{lang}` → remove the override (revert to platform); invalidate; audit `string.revert`.

- [ ] Steps: failing tests (override changes the resolved `t()` output after invalidation; revert restores platform text) → implement → PASS + ruff → commit `feat(5b): tenant string overrides admin + i18n invalidation`.

### Task 9: tenant config `/admin/tenants/{id}/config`

**Files:** Modify `admin_tenants.py`; schemas `ConfigOut`, `ConfigPutIn`; Test additions.

- `GET /admin/tenants/{tenant_id}/config` (owner/admin) → all `tenant_config` rows `{key: value_jsonb}`.
- `PUT /admin/tenants/{tenant_id}/config` (owner/admin) `{key, value}` → upsert (set updated_by). Audit `config.update`.

- [ ] Steps: failing tests (set + read back a config key) → implement → PASS + ruff → commit `feat(5b): tenant config admin`.

### Task 10: tenant plans CRUD `/admin/tenants/{id}/plans`

**Files:** Modify `admin_tenants.py`; reuse plan schemas (`SubscriptionPlanCreateIn`, etc. already exist) + domain plan helpers; Test additions.

- `GET /admin/tenants/{tenant_id}/plans` (owner/admin) → tenant's subscription + package plans (tenant_id == this tenant; NOT the global NULL ones).
- `POST .../plans/subscription` and `POST .../plans/package` (owner/admin) → create a tenant-scoped plan (set tenant_id). Audit `plan.create`.
- `PATCH .../plans/subscription/{plan_id}` / `.../package/{plan_id}` → update price/active/etc.; 404 if not this tenant's plan. Audit `plan.update`.
(Reuse the existing admin plan create/patch logic from the platform plans route if present, scoping tenant_id.)

- [ ] Steps: failing tests (create tenant sub+pkg plan; list returns only this tenant's; patch updates; cross-tenant plan_id 404) → implement → PASS + ruff → commit `feat(5b): tenant plans CRUD + audit`.

### Task 11: accounts list + balance `/admin/tenants/{id}/accounts`

**Files:** Modify `admin_tenants.py`; schemas `AccountSummaryOut`, `BalancePatchIn`; Test additions.

- `GET /admin/tenants/{tenant_id}/accounts?limit=&offset=` (owner/admin) → paginated account summaries (id, created_at, last_seen_at, balance package_credits + subscription_active_until).
- `PATCH /admin/tenants/{tenant_id}/accounts/{account_id}/balance` (owner/admin) `{package_credits?, subscription_active_until?}` → adjust balance (admin grant); 404 if account not in tenant. Audit `account.balance_adjust` with before/after.

- [ ] Steps: failing tests (list accounts; balance patch adjusts + audit; cross-tenant account 404) → implement → PASS + ruff → commit `feat(5b): tenant accounts list + balance admin + audit`.

---

## Phase 4 — Stats

### Task 12: per-tenant stats `/admin/tenants/{id}/stats`

**Files:** Create `src/quantuum/domain/stats.py`; Modify `admin_tenants.py`; schemas `TenantStatsOut`; Test `tests/test_stats.py` + route test.

`domain/stats.py: async def tenant_stats(session, tenant_id, *, period_days=30) -> dict` computing via SQL (spec §626):
- active_customers (accounts with last_seen_at within period),
- paid_customers (accounts with a `paid` payment ever / within period),
- dau/wau/mau (distinct accounts active in 1/7/30 days),
- requests_by_kind (count grouped by requests.kind in period),
- revenue_cents (sum paid payments amount in period) + mrr (sum of active subscription plan prices),
- llm_cost (sum blueprints.llm_tokens_in/out — for MVP report token totals; price table optional).
Keep each metric a clear SQL aggregation; `period_days` windows on `created_at`/`last_seen_at`.

Route `GET /admin/tenants/{tenant_id}/stats?period_days=30` (owner/admin) → TenantStatsOut. (Read-only → no audit.)

- [ ] Steps: failing tests — seed accounts/requests/payments/subscriptions for the tenant, assert each metric. Use fixed timestamps within/outside the window. → implement → PASS + ruff → commit `feat(5b): per-tenant real-time stats`.

### Task 13: platform stats + tenant breakdown `/admin/platform/stats`

**Files:** Modify `domain/stats.py` (`platform_stats(session, *, period_days)`), `admin_platform.py`; schemas `PlatformStatsOut`; Test additions.

`platform_stats` = the same metrics aggregated across all tenants + a per-tenant breakdown list + onboarding funnel (invites issued/used, active tenants). Route `GET /admin/platform/stats?period_days=` (superadmin).

- [ ] Steps: failing tests (aggregate matches sum of per-tenant; funnel counts invites) → implement → PASS + ruff → commit `feat(5b): platform stats + tenant breakdown + onboarding funnel`.

---

## Phase 5 — Platform admin

### Task 14: platform config/strings/superadmins

**Files:** Modify `admin_platform.py`; schemas; Test additions.

- `GET/PUT /admin/platform/config` (superadmin) → platform_config key/value. Audit (tenant_id NULL) `platform.config.update`.
- `GET/PUT /admin/platform/strings` (superadmin) `{key, lang, text}` → upsert platform_strings; invalidate ALL tenants' cache for that lang is overkill — for MVP `invalidate_i18n` is per-tenant; platform-string edits affect every tenant, so publish a global invalidate by deleting `i18n:*:{lang}` (scan) OR document that platform-string edits take effect within the 1h TTL. MVP: scan-delete `i18n:*:{lang}`. Audit `platform.string.update`.
- `GET /admin/platform/superadmins` + `POST` (grant is_superadmin to an account by id/email) + `DELETE` (revoke) (superadmin). Audit `platform.superadmin.grant/revoke`.

- [ ] Steps: failing tests (config roundtrip; platform string edit invalidates caches; superadmin grant/revoke) → implement → PASS + ruff → commit `feat(5b): platform config/strings/superadmins admin`.

### Task 15: platform tenants suspend/archive + audit-log read

**Files:** Modify `admin_platform.py`; schemas; Test additions.

- `POST /admin/platform/tenants/{tenant_id}/suspend` + `/archive` (superadmin) → set tenant.status; audit `platform.tenant.suspend/archive`.
- `GET /admin/platform/audit-log?tenant_id=&limit=&offset=` (superadmin) → list audit entries (all, or filtered by tenant). 
- Also add `GET /admin/tenants/{tenant_id}/audit-log` (owner/admin) → that tenant's entries only.

- [ ] Steps: failing tests (suspend/archive sets status + audit; audit-log lists entries; tenant audit-log scoped) → implement → PASS + ruff → commit `feat(5b): platform tenant suspend/archive + audit-log read`.

---

## Stage completion
- Run the FULL suite `uv run pytest -q` (per the test-run-scope rule, full suite at stage end) + `uv run ruff check .`.
- Holistic 5b review (auth coverage on every route, audit on every mutation, stats correctness, i18n invalidation on string/lang edits, migration chain linear).

## Self-review checklist
- Every tenant route guarded by `require_tenant_role` with correct roles (owner-only where spec says); superadmin override everywhere. ✓
- Every mutating route writes an `audit_log` entry. ✓
- String/language edits call `invalidate_i18n`. ✓
- Stats are read-only (no audit) and window correctly. ✓
- Migration `a6b7c8d9e0f1` chains off `f5e6a7b8c9d0`, single head. ✓

## Deploy notes
- `alembic upgrade head` for the audit_log table.
- New admin endpoints require owner/admin `tenant_roles` or superadmin; no new env.
