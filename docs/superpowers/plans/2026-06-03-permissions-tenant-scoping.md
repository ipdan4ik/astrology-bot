# Permissions & Tenant Scoping (Workstream D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make destructive and financial actions owner-only (admin keeps read + day-to-day ops), prevent cross-tenant account mutation and plan IDOR, harden superadmin lookup, and lock suspended/archived tenants out of management endpoints and webhook delivery.

**Architecture:** Locked decisions: destructive+financial = `owner`-only; admin keeps stats, feature toggles, branding, referral/gift config, and customer view. Fixes span the bot owner-console handlers (`roles=("owner",)`), the owner-users handlers (owner-only + cross-tenant guard), the HTTP API tenant routes (`require_tenant_role(("owner",))` + tenant-status gate), the plan getters (tenant scoping), the superadmin lookup (`.first()`), and the webhook/bot resolution (join `Tenant.status`).

**Tech Stack:** aiogram handlers + `authorize_tenant_action` (returns actor id or None), FastAPI deps (`require_tenant_role`, `current_account`), SQLAlchemy async, pytest (`uv run pytest`).

**Key patterns (verbatim from current code):**
- Bot authorization denial: `actor = await authorize_tenant_action(session, tg_user_id=..., tenant_id=...)` then `if actor is None: await query.answer(await i18n("owner.no_rights"), show_alert=True); return` (FSM variants use `message.answer(...)` + `state.clear()`). Changing `roles=("owner",)` makes an `admin` actor resolve to `None` → the same `owner.no_rights` denial.
- `authorize_tenant_action(session, *, tg_user_id, tenant_id, roles=("owner","admin"))` lives in `src/quantuum/domain/owner_console.py:54`.
- `get_customer_card(session, tenant_id, account_id)` (`src/quantuum/domain/accounts.py:179`) returns `None` when `acc.tenant_id != tenant_id` — the cross-tenant guard.
- `require_tenant_role(roles)` factory in `src/quantuum/api/deps.py:40`.

**Test command:** `uv run pytest <path> -v`. asyncio auto mode (no decorator); fixtures `session`, `default_tenant`. For each bot/API task, READ the named existing test file first and mirror its helper for building an owner vs admin actor (grant role via the file's existing role-grant helper). Do NOT weaken assertions.

---

### Task 1: `find_superadmin_by_tg` uses `.first()`

**Files:**
- Modify: `src/quantuum/auth/identity.py:97`
- Test: `tests/test_api_auth.py` or wherever `find_superadmin_by_tg` is tested (`grep -rln find_superadmin_by_tg tests/`)

- [ ] **Step 1: Write the failing test**

Add a test that links TWO `AccountIdentity` rows (same `tg_user_id`, `provider="tg_chat"`) to TWO superadmin accounts, then calls `find_superadmin_by_tg` and asserts it returns an account (not raises). With `scalar_one_or_none` this raises `MultipleResultsFound`; with `.first()` it returns one.

```python
async def test_find_superadmin_by_tg_tolerates_duplicates(session):
    from quantuum.db.models import Account, AccountIdentity
    from quantuum.auth.identity import find_superadmin_by_tg

    for i in range(2):
        acc = Account(is_superadmin=True, status="active")
        session.add(acc)
        await session.flush()
        session.add(AccountIdentity(
            account_id=acc.id, provider="tg_chat", provider_user_id="dup_sa",
        ))
    await session.commit()

    result = await find_superadmin_by_tg(session, "dup_sa")
    assert result is not None and result.is_superadmin
```

NOTE: adapt `AccountIdentity(...)` field names to the model (grep `class AccountIdentity`). If the column is `tg_user_id` instead of `provider_user_id`, use the real one.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <test file> -k tolerates_duplicates -v`
Expected: FAIL — `MultipleResultsFound`.

- [ ] **Step 3: Implement**

In `src/quantuum/auth/identity.py`, change line 97 from:

```python
    identity = result.scalar_one_or_none()
```

to:

```python
    identity = result.scalars().first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest <test file> -k tolerates_duplicates -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/auth/identity.py <test file>
git commit -m "fix(auth): find_superadmin_by_tg tolerates duplicate identities"
```

---

### Task 2: Owner-only destructive actions in owner_console (pause/resume/delete)

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_console.py` — pause (line 216-218), resume (248-250), delete-start (374-376), delete-confirm (407-409)
- Test: `tests/test_owner_console_handlers.py`

- [ ] **Step 1: Inspect the test file**

Read `tests/test_owner_console_handlers.py`; find its helper for seeding an actor with a role (e.g. `_seed_account_with_role(session, tenant, role=...)`). You'll reuse it to build an `admin` actor.

- [ ] **Step 2: Write the failing tests**

For pause and delete-start, add a test that an `admin` actor is DENIED (gets `owner.no_rights`, and the tenant status is unchanged). Mirror the existing owner happy-path test's call shape (callback object, i18n). Example for pause:

```python
async def test_admin_cannot_pause_tenant(session, ...):
    # build an admin actor for `tenant` (NOT owner), reuse this file's helpers
    # build the OwnerManageCb(action="pause", tenant_id=tenant.id) callback + query mock
    await on_manage_pause(query, callback_data, i18n)
    # denied:
    assert any("owner.no_rights" in str(c.args) for c in query.answer.await_args_list) \
        or query.answer.await_args.kwargs.get("show_alert")  # adapt to i18n shape
    # tenant still active:
    t = await session.get(Tenant, tenant.id)
    await session.refresh(t)
    assert t.status == "active"
```

Add an analogous `test_admin_cannot_delete_tenant` (delete-start handler). Also confirm (or add) that an OWNER still succeeds (mirror existing owner tests — they likely already cover the success path; if so you don't need to duplicate).

NOTE: match how this file asserts denial — if existing denial tests check the rendered `owner.no_rights` string via `build_translator`, do the same.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_owner_console_handlers.py -k "admin_cannot" -v`
Expected: FAIL — admin currently passes (default roles include admin), so the tenant gets paused/archived.

- [ ] **Step 4: Implement**

Add `roles=("owner",)` to the four `authorize_tenant_action` calls:
- pause (`on_manage_pause`, ~line 216):
  ```python
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id,
            roles=("owner",),
        )
  ```
- resume (`on_manage_resume`, ~line 248): same `roles=("owner",)` addition.
- delete-start (`on_manage_delete`, ~line 374): same.
- delete-confirm (`on_delete_confirm`, ~line 407): same.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_owner_console_handlers.py -v`
Expected: PASS (new denial tests + existing owner-success tests still green).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/owner_console.py tests/test_owner_console_handlers.py
git commit -m "fix(owner): pause/resume/delete are owner-only"
```

---

### Task 3: Owner-only financial actions in owner_users (grant/ban/unban)

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_users.py` — grant-start (177-179), grant-confirm (206-208), ban-start (241-243), ban-confirm (272-274), unban (305-307)
- Test: `tests/test_owner_users_handlers.py`

- [ ] **Step 1: Inspect the test file**

Read `tests/test_owner_users_handlers.py`; it has `_owner(session, tenant)`. Find or add an `_admin(session, tenant)` that grants the `admin` role (mirror `_owner` but with role `"admin"`).

- [ ] **Step 2: Write the failing tests**

Add denial tests for an `admin` actor on grant-start, ban-start, and unban (and the FSM confirm steps if practical). Assert `owner.no_rights` and that the side effect did NOT happen (no credit change / no ban). Example for unban:

```python
async def test_admin_cannot_unban(session, default_tenant):
    # admin actor; a banned target account in this tenant
    # call on_user_unban(query, callback_data, i18n)
    # assert owner.no_rights and target still banned (ban_reason unchanged)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_owner_users_handlers.py -k "admin_cannot" -v`
Expected: FAIL — admin currently allowed.

- [ ] **Step 4: Implement**

Add `roles=("owner",)` to all five `authorize_tenant_action` calls in `owner_users.py` (grant-start, grant-confirm, ban-start, ban-confirm, unban). Each currently reads e.g.:

```python
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
```

Change to add `roles=("owner",)`:

```python
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id,
            roles=("owner",),
        )
```

(For the FSM message handlers the first arg is `str(message.from_user.id)` — keep that, only add `roles=("owner",)`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_owner_users_handlers.py -v`
Expected: PASS (existing owner-success tests still green).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/owner_users.py tests/test_owner_users_handlers.py
git commit -m "fix(owner): grant/ban/unban are owner-only"
```

---

### Task 4: Cross-tenant ban/unban guard (bot)

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_users.py` — ban-start (`on_user_ban_start`), ban-confirm (`on_user_ban_reason`), unban (`on_user_unban`)
- Test: `tests/test_owner_users_handlers.py`

**Context:** an owner could pass an `account_id` belonging to ANOTHER tenant. `is_tenant_staff` only checks staff membership, not that the target belongs to this tenant, so a foreign account passes. Add a `get_customer_card(session, tenant_id, account_id) is None → deny` guard (it validates `acc.tenant_id == tenant_id`). The grant handler already does this; mirror it.

- [ ] **Step 1: Write the failing test**

```python
async def test_owner_cannot_ban_cross_tenant_account(session, default_tenant):
    from quantuum.db.models import Account, Tenant
    # owner of default_tenant (reuse _owner)
    owner_tg = ...  # the owner's tg id used in the query mock
    # a victim account in a DIFFERENT tenant
    other = Tenant(slug="d-other", display_name="Other"); session.add(other)
    await session.flush()
    victim = Account(tenant_id=other.id, status="active"); session.add(victim)
    await session.commit()

    # OwnerUserCb(action="ban", tenant_id=default_tenant.id, account_id=victim.id)
    await on_user_ban_start(query, callback_data, state, i18n)
    # denied (no FSM state set / a not-found message), victim NOT banned:
    v = await session.get(Account, victim.id); await session.refresh(v)
    assert v.status == "active" and v.ban_reason is None
```

Add an analogous `test_owner_cannot_unban_cross_tenant_account` for `on_user_unban`.

NOTE: choose the denial i18n key consistent with the file's conventions — reuse an existing "not found"/"no_rights" key. If none fits, add a key `owner.user.not_found` (ru/en in `seed_strings.py` + all 8 translation files — see Workstream A-handlers Task 1 for the file list) and use it. Prefer reusing `owner.no_rights` if the team treats a foreign account as "no rights over it".

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_owner_users_handlers.py -k cross_tenant -v`
Expected: FAIL — victim gets banned.

- [ ] **Step 3: Implement**

In `on_user_ban_start`, after the `authorize_tenant_action` check and before/with the `is_tenant_staff` check, add:

```python
        if await get_customer_card(session, tenant_id, account_id) is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
```

In `on_user_ban_reason` (FSM), add the same guard (using `message.answer(...)` + `await state.clear()` + `return`). In `on_user_unban`, add it (using `query.answer(...)` + `return`). Import `get_customer_card` at the top if not already imported (`from quantuum.domain.accounts import get_customer_card` — check existing imports; the grant handler already uses it so it's likely imported).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_owner_users_handlers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/owner_users.py tests/test_owner_users_handlers.py
git commit -m "fix(owner): reject ban/unban of cross-tenant accounts"
```

---

### Task 5: Owner-only API for pricing, balance, ban/unban

**Files:**
- Modify: `src/quantuum/api/routes/admin_tenants.py` — change the dependency on these routes from `require_tenant_role(("owner", "admin"))` to `require_tenant_role(("owner",))`:
  - `POST /{tenant_id}/plans/subscription` (~line 734)
  - `POST /{tenant_id}/plans/package` (~line 768)
  - `PATCH /{tenant_id}/plans/subscription/{plan_id}` (~line 802)
  - `PATCH /{tenant_id}/plans/package/{plan_id}` (~line 837)
  - `PATCH /{tenant_id}/accounts/{account_id}/balance` (~line 911)
  - `POST /{tenant_id}/accounts/{account_id}/ban` (~line 1019)
  - `POST /{tenant_id}/accounts/{account_id}/unban` (~line 1048)
  - Leave `GET /{tenant_id}/plans` (~line 712) as `("owner", "admin")` — listing is read/day-to-day.
- Test: `tests/test_api_admin_tenants.py`

- [ ] **Step 1: Inspect the test file**

Read `tests/test_api_admin_tenants.py`; find how it builds an authorized `admin` vs `owner` token/account (role grant helper). You'll add admin-denied tests.

- [ ] **Step 2: Write the failing tests**

For the balance-patch and ban endpoints, add a test that an `admin` token gets `403` (and the resource is unchanged). Example:

```python
async def test_admin_cannot_patch_balance(client, session, ...):
    # admin account+token for tenant T, a target account in T
    resp = await client.patch(
        f"/{tenant_id}/accounts/{account_id}/balance",
        json={"package_credits": 50},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403
```

Add an analogous `test_admin_cannot_ban_account` and `test_admin_cannot_create_subscription_plan`. Mirror the file's existing client/token fixtures. Also confirm OWNER still gets 2xx on at least one of these (existing owner tests likely cover it).

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_admin_tenants.py -k "admin_cannot" -v`
Expected: FAIL — admin currently authorized (200/201).

- [ ] **Step 4: Implement**

In `src/quantuum/api/routes/admin_tenants.py`, change `Depends(require_tenant_role(("owner", "admin")))` to `Depends(require_tenant_role(("owner",)))` on the seven routes listed above. Leave the GET list route and any read/feature/branding routes untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_admin_tenants.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/api/routes/admin_tenants.py tests/test_api_admin_tenants.py
git commit -m "fix(api): pricing, balance, ban/unban routes are owner-only"
```

---

### Task 6: Plan IDOR — tenant-scope the plan getters

**Files:**
- Modify: `src/quantuum/domain/plans.py:30-37` (`get_subscription_plan`, `get_package_plan`)
- Modify call sites: `src/quantuum/api/routes/me.py:546,559`; `src/quantuum/domain/billing.py:234,241`
- Test: `tests/test_api_billing_me.py` (or wherever buy_subscription/buy_package is tested — grep)

- [ ] **Step 1: Write the failing test**

A buyer in tenant A requests a plan belonging to tenant B → must 404. Mirror the buy-endpoint test setup.

```python
async def test_buy_subscription_rejects_other_tenant_plan(client, session, default_tenant):
    from quantuum.db.models import SubscriptionPlan, Tenant
    other = Tenant(slug="idor-other", display_name="Other"); session.add(other)
    await session.flush()
    foreign = SubscriptionPlan(
        tenant_id=other.id, name="Foreign", period_days=30,
        price_cents=500, currency="XTR", active=True,
    )
    session.add(foreign)
    await session.commit()
    # buyer account+token in default_tenant
    resp = await client.post(
        "/me/subscriptions", json={"plan_id": foreign.id},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 404
```

NOTE: adapt the route prefix/path and the buyer-token fixture to the test file's conventions. Add an analogous package test if the file pattern makes it cheap.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <test file> -k rejects_other_tenant_plan -v`
Expected: FAIL — returns 201/200 (or whatever success is), because the getter ignores tenant.

- [ ] **Step 3: Implement**

In `src/quantuum/domain/plans.py`, add an optional `tenant_id` keyword and the scoping rule (allow platform plans where `tenant_id IS NULL`, or plans owned by the caller's tenant):

```python
async def get_subscription_plan(
    session, plan_id: int, *, tenant_id: int | None = None
) -> SubscriptionPlan | None:
    plan = await session.get(SubscriptionPlan, plan_id)
    if plan is None or not plan.active:
        return None
    if tenant_id is not None and plan.tenant_id is not None and plan.tenant_id != tenant_id:
        return None
    return plan


async def get_package_plan(
    session, plan_id: int, *, tenant_id: int | None = None
) -> PackagePlan | None:
    plan = await session.get(PackagePlan, plan_id)
    if plan is None or not plan.active:
        return None
    if tenant_id is not None and plan.tenant_id is not None and plan.tenant_id != tenant_id:
        return None
    return plan
```

Update call sites to pass the tenant:
- `src/quantuum/api/routes/me.py:546`: `plan = await get_subscription_plan(session, body.plan_id, tenant_id=account.tenant_id)`
- `src/quantuum/api/routes/me.py:559`: `plan = await get_package_plan(session, body.plan_id, tenant_id=account.tenant_id)`
- `src/quantuum/domain/billing.py:234`: `plan = await get_subscription_plan(session, plan_id, tenant_id=payment.tenant_id)`
- `src/quantuum/domain/billing.py:241`: `plan = await get_package_plan(session, plan_id, tenant_id=payment.tenant_id)`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest <test file> -k rejects_other_tenant_plan -v`
Expected: PASS

- [ ] **Step 5: Run plan + billing suites**

Run: `uv run pytest tests/test_billing_fulfill.py tests/test_billing_crediting.py -v` and any `test_*plans*` file.
Expected: all PASS (platform plans with `tenant_id IS NULL` still resolve; same-tenant plans still resolve).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/plans.py src/quantuum/api/routes/me.py src/quantuum/domain/billing.py <test file>
git commit -m "fix(plans): tenant-scope plan getters to prevent cross-tenant IDOR"
```

---

### Task 7: Lock suspended/archived tenants out of management API

**Files:**
- Modify: `src/quantuum/api/deps.py:40-66` (`require_tenant_role._dep`)
- Test: `tests/test_api_admin_tenants.py`

**Context:** `require_tenant_role` checks the account's role but not the tenant's `status`. A suspended or archived tenant should reject management calls. Superadmins still bypass (they may need to act on any tenant).

- [ ] **Step 1: Write the failing test**

```python
async def test_suspended_tenant_rejects_management(client, session, ...):
    # owner + token for tenant T; set T.status = "suspended"
    t = await session.get(Tenant, tenant_id); t.status = "suspended"
    session.add(t); await session.commit()
    resp = await client.get(
        f"/{tenant_id}/plans",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 403
```

NOTE: use a route guarded by `require_tenant_role` that the file already exercises; `GET /{tenant_id}/plans` is convenient. Add an `archived` variant if cheap.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_admin_tenants.py -k suspended_tenant_rejects -v`
Expected: FAIL — returns 200.

- [ ] **Step 3: Implement**

In `src/quantuum/api/deps.py`, in `require_tenant_role._dep`, after the superadmin bypass and before/after the role check, add a tenant-status gate. Import `Tenant`:

```python
from quantuum.db.models import Account, Tenant
```

```python
    async def _dep(
        tenant_id: int,
        account: Account = Depends(current_account),
        session: AsyncSession = Depends(get_session),
    ) -> Account:
        if account.is_superadmin:
            return account
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.status != "active":
            raise HTTPException(status_code=403, detail="tenant not active")
        if account.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="forbidden")
        for role in roles:
            if await account_has_role(session, tenant_id=tenant_id, account_id=account.id, role=role):
                return account
        raise HTTPException(status_code=403, detail="insufficient role")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_admin_tenants.py -k suspended_tenant_rejects -v`
Expected: PASS

- [ ] **Step 5: Run the full admin_tenants API suite**

Run: `uv run pytest tests/test_api_admin_tenants.py -v`
Expected: all PASS. If existing tests created tenants without setting status, they default to `"active"` so they remain authorized.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/api/deps.py tests/test_api_admin_tenants.py
git commit -m "fix(api): management endpoints reject non-active tenants"
```

---

### Task 8: Stop webhook/bot delivery for non-active tenants

**Files:**
- Modify: `src/quantuum/domain/tenants.py` — `resolve_tenant_id_by_bot` (74-80) and `get_tenant_bot_by_webhook_secret` (83-89): join `Tenant` and require `Tenant.status == "active"`.
- Test: `tests/test_tenant_resolution.py` and/or `tests/test_api_webhook.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_webhook_secret_ignores_suspended_tenant(session):
    from quantuum.db.models import Tenant, TenantBot
    from quantuum.domain.tenants import get_tenant_bot_by_webhook_secret
    t = Tenant(slug="susp", display_name="S", status="suspended")
    session.add(t); await session.flush()
    session.add(TenantBot(
        tenant_id=t.id, bot_telegram_id=999001, status="active",
        webhook_secret_path="susp-secret",
        # adapt required TenantBot columns (token enc, transport, etc.)
    ))
    await session.commit()
    bot = await get_tenant_bot_by_webhook_secret(session, "susp-secret")
    assert bot is None
```

NOTE: grep `class TenantBot` in `db/models.py` for required NOT NULL columns and set them. Mirror how `tests/test_tenant_resolution.py` builds a `TenantBot`. Add an analogous `resolve_tenant_id_by_bot` test if cheap.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <test file> -k ignores_suspended_tenant -v`
Expected: FAIL — returns the bot (no tenant-status check).

- [ ] **Step 3: Implement**

In `src/quantuum/domain/tenants.py`, ensure `Tenant` is imported, then add a join + status filter. For `get_tenant_bot_by_webhook_secret`:

```python
async def get_tenant_bot_by_webhook_secret(session, secret: str) -> TenantBot | None:
    result = await session.execute(
        select(TenantBot)
        .join(Tenant, Tenant.id == TenantBot.tenant_id)
        .where(
            TenantBot.webhook_secret_path == secret,
            TenantBot.status == "active",
            Tenant.status == "active",
        )
    )
    return result.scalar_one_or_none()
```

For `resolve_tenant_id_by_bot`:

```python
async def resolve_tenant_id_by_bot(session, bot_telegram_id: int) -> int | None:
    result = await session.execute(
        select(TenantBot.tenant_id)
        .join(Tenant, Tenant.id == TenantBot.tenant_id)
        .where(
            TenantBot.bot_telegram_id == bot_telegram_id,
            TenantBot.status == "active",
            Tenant.status == "active",
        )
    )
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest <test file> -k ignores_suspended_tenant -v`
Expected: PASS

- [ ] **Step 5: Run resolution + webhook suites**

Run: `uv run pytest tests/test_tenant_resolution.py tests/test_api_webhook.py -v`
Expected: all PASS. NOTE: existing tests that build a `TenantBot` but no `Tenant` row, or a `Tenant` without `status`, may now resolve to None. If a legitimate existing test breaks because its fixture omitted a `Tenant` row or left status unset, FIX THE FIXTURE to add an active `Tenant` (the resolution now correctly requires one) — do not revert the join.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/tenants.py <test files>
git commit -m "fix(tenants): webhook/bot resolution requires an active tenant"
```

---

### Task 9: Stage regression — full suite

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (prior baseline 2020 passed + the new tests from this plan).

- [ ] **Step 2: If anything fails**

Investigate. The most likely regressions are existing tests that relied on (a) admin being able to do now-owner-only actions, or (b) tenant resolution working without an active `Tenant` row. For (a): if the existing test's INTENT was "admin can do X" and X is now owner-only by design, update the test to use an owner actor (the behavior change is intended per the locked decision) — but verify the test was asserting a now-obsolete permission, don't blindly flip it. For (b): add the missing active `Tenant` to the fixture. Do NOT weaken security assertions.

- [ ] **Step 3: Commit** any fixture/test fixes with a clear message.

---

## Notes / scope

- Admin RETAINS: stats, feature toggles, branding, referral/gift config, list users, customer view. Only delete/pause/resume/transfer (transfer already owner-only) and grant/ban/unban + API pricing/balance/ban became owner-only.
- Suspended tenants are still visible+resumable via the BOT owner-console (`managed_tenants` includes suspended; resume uses `authorize_tenant_action`, not `require_tenant_role`), so locking the management API for suspended tenants does not strand owners.
- After this plan, update the `audit-fix-sweep-progress` memory: D DONE. Spec order next: C → E → F → G.
