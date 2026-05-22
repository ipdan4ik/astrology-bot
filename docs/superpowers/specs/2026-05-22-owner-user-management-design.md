# Owner User Management — Design

**Date:** 2026-05-22
**Status:** Approved (design)
**Topic:** Let a tenant owner/admin manage the customers of their own bot from the Telegram owner console: list users, adjust their credits, and ban/unban them.

## Goal

A tenant owner or admin, from the Telegram bot owner console, can:

1. **View the list of users** (customers) of their own bot, paginated.
2. **Adjust a user's credits** — add or deduct prepaid blueprint credits (`package_credits`), clamped at zero.
3. **Ban / unban a user** — a ban records a reason, blocks the user from using the bot, and is reversible.

Scope is **tenant-scoped** (SP2 "manage own bot"): an owner/admin acts only on accounts inside a tenant where they hold the `owner`/`admin` role. Platform-wide superadmin user management is **out of scope** (that is SP1).

## Background — current state

- **Owner console (bot):** `src/quantuum/bot/handlers/owner_console.py` — `/tenants` lists the tenants a user manages; `/manage <slug>` shows a tenant card with inline buttons (stats / pause / resume / transfer / delete). Callbacks use `OwnerManageCb(action, tenant_id)`. Every callback re-authorizes via `authorize_tenant_action(session, tg_user_id=..., tenant_id=...)` (→ `owner.no_rights` on failure) and writes `record_audit(...)`. Multi-step input uses aiogram FSM (`/transfer`, delete-confirm). This file is already ~352 lines and is tenant-scoped.
- **Authorization:** `src/quantuum/domain/owner_console.py` — `managed_tenants`, `account_id_for_role`, `authorize_tenant_action`, `resolve_managed_tenant_by_slug`. Roles via `src/quantuum/domain/tenants.py` (`account_has_role`, `grant_role`, ...).
- **Account model** (`src/quantuum/db/models.py:88`): `Account(id, tenant_id, is_superadmin, status="active" # active|disabled, preferred_lang, last_seen_at, created_at)`. No ban-reason field today. A user's display name lives in `NatalProfile.full_name` (one per account, may be absent). The user's Telegram id is `AccountIdentity(provider="tg_chat").provider_user_id`.
- **Quota / credits** (`src/quantuum/db/models.py:262`): `AccountBalance(account_id PK, free_trial_used, subscription_active_until, package_credits, updated_at)`. `package_credits` is the only token-like balance. `consume_quota` (`domain/quota.py`) spends trial → subscription → package.
- **Ban enforcement gap:** `current_account()` (`api/deps.py:29`) already rejects `status != "active"` with HTTP 401. But the **bot** `AccountMiddleware` (`src/quantuum/bot/middleware/account.py`) does **not** check `status`, so a disabled account is still served by the bot today. A real ban requires adding this check.
- **HTTP admin API** (`src/quantuum/api/routes/admin_tenants.py`, prefix `/admin/tenants`, dep `require_tenant_role(("owner","admin"))`):
  - `GET /{tenant_id}/accounts` — list accounts (limit/offset) → `AccountSummaryOut`.
  - `GET /{tenant_id}/accounts/{account_id}` — account detail.
  - `PATCH /{tenant_id}/accounts/{account_id}/balance` — set `package_credits` / `subscription_active_until` (absolute), audited as `account.balance_adjust`.
  - **No ban/unban endpoint exists.**
- **i18n** (post-multilanguage): 10 languages. Adding any new key requires `ru`+`en` inline in `BASE_STRINGS` (`src/quantuum/i18n/seed_strings.py`) **and** an entry for that key in every per-language file `src/quantuum/i18n/translations/{es,fr,pt,it,de,tr,zh,hi}.py`. Three tests enforce this (`tests/test_i18n_translations.py`): every key has all 10 platform langs, every translation file's key set equals `BASE_STRINGS`, and placeholder tokens match across languages.

## Design

### 1. Data model + migration

- Reuse `Account.status` (`active`|`disabled`); `disabled` means banned.
- Add a nullable column `Account.ban_reason: str | None = None` (after `status` in the model). Banned = `status="disabled"` **and** `ban_reason` set; unban sets `status="active"`, `ban_reason=None`.
- New alembic migration with `down_revision="f6a7b8c9d0e1"` (the current head): `op.add_column("accounts", sa.Column("ban_reason", sa.String(), nullable=True))`; downgrade drops it. The test schema is built from `SQLModel.metadata`, so the model change alone exercises the column in tests; the migration is the production path.

### 2. Domain layer (`src/quantuum/domain/accounts.py`)

Add pure, session-based functions (reused by bot, HTTP, and tests):

- `list_tenant_customers(session, tenant_id, *, limit, offset) -> list[CustomerRow]` — left-joins `AccountBalance`, `NatalProfile` (for `full_name`), and `AccountIdentity[tg_chat]` (for `tg_user_id`), ordered by `Account.id`. `CustomerRow` is a small dataclass: `account_id, full_name | None, tg_user_id | None, package_credits, status`.
- `count_tenant_customers(session, tenant_id) -> int` — for paging math.
- `get_customer_card(session, tenant_id, account_id) -> CustomerCard | None` — returns `account_id, full_name, tg_user_id, package_credits, subscription_active_until, free_trial_used, status, ban_reason, last_seen_at`; `None` if the account is missing or not in this tenant.
- `adjust_package_credits(session, account_id, delta: int) -> int` — creates the `AccountBalance` row if missing; sets `package_credits = max(0, package_credits + delta)`; updates `updated_at`; returns the new balance. **Flush, not commit** (caller commits, consistent with `record_audit`).
- `set_account_ban(session, account_id, *, reason: str) -> None` — `status="disabled"`, `ban_reason=reason`.
- `clear_account_ban(session, account_id) -> None` — `status="active"`, `ban_reason=None`.
- `is_tenant_staff(session, tenant_id, account_id) -> bool` — true if the account holds `owner` or `admin` in the tenant (via `account_has_role`); used to forbid banning staff/self.

### 3. Bot flow (`src/quantuum/bot/handlers/owner_users.py` — new file)

New callback in `src/quantuum/bot/ui/callbacks.py`:

```python
class OwnerUserCb(CallbackData, prefix="ousr"):
    action: str          # list | open | grant | ban | unban
    tenant_id: int = 0
    account_id: int = 0
    page: int = 0
```

(`prefix="ousr"` is unused today; packed strings like `ousr:open:12:3456:0` are well under Telegram's 64-byte limit.)

**Entry point** — add one button to the existing `/manage` tenant card in `owner_console.py`:
`owner.manage.kb.users` → `OwnerUserCb(action="list", tenant_id=tenant.id, page=0)`.

**List** (`action="list"`): authorize; `PAGE_SIZE = 8`; fetch `list_tenant_customers(limit=PAGE_SIZE, offset=page*PAGE_SIZE)` and `count_tenant_customers`. Render a header (`owner.users.header`) and one button per user (`owner.users.row` label: `{name} · {credits}💎{banned_mark}`, where name falls back to `owner.users.unnamed` = `user #{id}`) → `OwnerUserCb(action="open", tenant_id, account_id)`. Append a nav row: ◀️ (`page-1`, only if `page>0`), ▶️ (`page+1`, only if more remain), ⬅️ back. Empty tenant → `owner.users.empty`.

**Card** (`action="open"`): authorize; `get_customer_card`; render `owner.user.card` (name, Telegram id, credits, subscription, free-trial, status; if banned, a `owner.user.card.banned` line with the reason). Buttons: `owner.user.kb.grant` → `action="grant"`; if active `owner.user.kb.ban` → `action="ban"`, else `owner.user.kb.unban` → `action="unban"`; `owner.user.kb.back` → `action="list"` (back to the list, page 0). Missing account → `owner.user.not_found`.

**Credits (FSM `OwnerUserAdmin.awaiting_credit_amount`)** (`action="grant"`): authorize; store `tenant_id`+`account_id` in FSM; prompt `owner.user.grant.prompt`. On reply: parse a signed integer (`int(text)`; reject with `owner.user.grant.invalid`, stay in state). Re-authorize, call `adjust_package_credits`, `record_audit(action="account.credits_adjust", entity_type="account", entity_id=account_id, payload={"delta": delta, "before": ..., "after": ...})`, commit, clear state, reply `owner.user.grant.done` (new balance). `/cancel` → `owner.user.cancelled`.

**Ban (FSM `OwnerUserAdmin.awaiting_ban_reason`)** (`action="ban"`): authorize; **guard:** if `is_tenant_staff(tenant_id, account_id)` → `owner.user.ban.staff_blocked` and stop (this also blocks self-ban, since the actor is staff). Otherwise store ids in FSM, prompt `owner.user.ban.prompt`. On reply (the reason text; empty → `owner.user.ban.invalid`, stay): re-authorize, re-check staff guard, `set_account_ban(reason=text)`, `record_audit(action="account.ban", entity_id=account_id, payload={"reason": text})`, commit, clear state, reply `owner.user.ban.done`.

**Unban** (`action="unban"`): authorize; `clear_account_ban`; `record_audit(action="account.unban", entity_id=account_id)`; commit; reply `owner.user.unban.done`. One tap (reversible, no confirm).

All handlers follow the `owner_console.py` conventions: open a session via `get_sessionmaker()`, `authorize_tenant_action(...)` → `owner.no_rights` (`show_alert=True`) on failure, `record_audit`, `await query.answer()`. Register the new router wherever `owner_console.router` is registered (bot app + master app, mirroring the existing registration).

### 4. Ban enforcement (`src/quantuum/bot/middleware/account.py`)

After resolving the account (and before building the translator / calling the handler): if `account.status == "disabled"`, build the translator for the user's language, send `account.banned.notice` (interpolating `ban_reason`; if reason is null, omit it) via the event's `answer` if available, and **return without calling the handler**. This blocks every interaction (messages and callbacks) for a banned user. Owners/admins are never banned (staff guard), so they are unaffected.

### 5. HTTP parity (`src/quantuum/api/routes/admin_tenants.py`)

Add two endpoints next to the existing accounts routes, dep `require_tenant_role(("owner","admin"))`:

- `POST /{tenant_id}/accounts/{account_id}/ban` body `{ "reason": str }` → 404 if account not in tenant; 409 (`detail="cannot ban staff"`) if `is_tenant_staff`; else `set_account_ban`, `record_audit(action="account.ban", payload={"reason": reason})`, commit; returns the account detail.
- `POST /{tenant_id}/accounts/{account_id}/unban` → `clear_account_ban`, `record_audit(action="account.unban")`, commit; returns the account detail.

Credit grant and listing already exist via the balance PATCH and the accounts list, so no new credit endpoint is added. `AccountDetailOut` gains `status` and `ban_reason` fields so the ban state is visible over HTTP.

### 6. i18n keys

Add these keys with `ru`+`en` inline in `BASE_STRINGS`, plus an entry in each of the 8 translation files (authored by per-language translation subagents, mirroring the multilanguage feature). Placeholders are noted; they must be copied verbatim into every language.

- `owner.manage.kb.users` — button on the tenant card.
- `owner.users.header` — `{display_name}`.
- `owner.users.empty`.
- `owner.users.row` — `{name}`, `{credits}` (button label).
- `owner.users.unnamed` — `{id}` (name fallback).
- `owner.users.nav.prev`, `owner.users.nav.next`, `owner.users.nav.back`.
- `owner.user.card` — `{name}`, `{tg_id}`, `{credits}`, `{subscription}`, `{status}`.
- `owner.user.card.banned` — `{reason}`.
- `owner.user.not_found`.
- `owner.user.kb.grant`, `owner.user.kb.ban`, `owner.user.kb.unban`, `owner.user.kb.back`.
- `owner.user.grant.prompt`, `owner.user.grant.invalid`, `owner.user.grant.done` — `{credits}`.
- `owner.user.ban.prompt`, `owner.user.ban.invalid`, `owner.user.ban.done`, `owner.user.ban.staff_blocked`.
- `owner.user.unban.done`.
- `owner.user.cancelled`.
- `account.banned.notice` — `{reason}` (sent by the middleware to a banned user).

`ensure_base_strings` is INSERT-ONLY, so these auto-seed on next bootstrap; no cache invalidation needed (new keys have no warm cache).

### 7. Error handling / edge cases

- Caller lacks the role (changed since the tap) → `owner.no_rights`; re-authorized at every step including FSM apply time.
- Banning staff or yourself → `owner.user.ban.staff_blocked`; enforced in both bot and HTTP.
- Credit deduct below zero → clamped at 0 (never negative).
- Grant on an account with no `AccountBalance` row → row is created.
- `account_id` not in this tenant → `owner.user.not_found` (bot) / 404 (HTTP).
- Pagination past the end → empty page (no crash); ▶️ hidden when no more rows.
- User with no `NatalProfile` → name falls back to `owner.users.unnamed`.
- Already-banned account on unban / already-active on ban → idempotent (no error).

### 8. Testing

- **Domain** (`tests/test_accounts_admin_domain.py`): `adjust_package_credits` add/deduct/clamp/creates-row; `set_account_ban`/`clear_account_ban` set fields; `is_tenant_staff` true for owner/admin, false for customer; `list_tenant_customers`/`count_tenant_customers` pagination + name/tg_id/credits mapping.
- **Bot handlers** (`tests/test_owner_users_handlers.py`): list renders rows + nav; open renders card; grant FSM (valid signed int adjusts; invalid rejected); ban FSM (reason stored, status disabled; staff guard blocks); unban flips back; non-authorized actor → `owner.no_rights`. Mirror `tests/test_owner_console_handlers.py` (FakeMessage/FakeCallbackQuery + monkeypatched `get_sessionmaker`, `build_translator`).
- **Middleware** (`tests/test_account_middleware_ban.py`): disabled account → notice sent, handler not called; active account → handler called.
- **HTTP** (extend `tests/test_api_admin_tenants.py`): ban/unban happy path; `customer_headers`/`other_tenant_headers` → 403; staff target → 409; unknown account → 404; `AccountDetailOut` exposes `status`/`ban_reason`.
- **i18n** (`tests/test_i18n_translations.py`): existing completeness + parity tests cover the new keys once all 10 languages are filled in.

## Out of scope

- Platform-wide (superadmin) cross-tenant user management — SP1.
- Editing subscription time or other balance fields from the bot (HTTP `PATCH balance` already does this).
- Bulk actions, search-by-name/free-text filtering, CSV export.
- Proactively messaging a user the instant they're banned (they see `account.banned.notice` on their next interaction).
- Temporary/timed bans, ban history UI beyond the audit log.

## Files touched (summary)

- `src/quantuum/db/models.py` — `Account.ban_reason` column.
- `alembic/versions/<new>_account_ban_reason.py` — new migration (down_revision `f6a7b8c9d0e1`).
- `src/quantuum/domain/accounts.py` — list/count/card/adjust/ban/unban/staff helpers.
- `src/quantuum/bot/ui/callbacks.py` — `OwnerUserCb`.
- `src/quantuum/bot/handlers/owner_users.py` — new per-user console flow (+ router registration).
- `src/quantuum/bot/handlers/owner_console.py` — 👥 Users button on the `/manage` card.
- `src/quantuum/bot/middleware/account.py` — block disabled accounts.
- `src/quantuum/api/routes/admin_tenants.py` — ban/unban endpoints; `AccountDetailOut` status/ban_reason.
- `src/quantuum/i18n/seed_strings.py` + `src/quantuum/i18n/translations/{es,fr,pt,it,de,tr,zh,hi}.py` — new keys × 10 langs.
- Tests under `tests/`.
