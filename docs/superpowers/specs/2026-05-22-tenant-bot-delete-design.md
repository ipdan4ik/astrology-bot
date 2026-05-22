# Tenant-bot deletion (owner self-service) — Design

> Sub-project 2/3 of the management/i18n feature wave (build order 3 → 2 → 1).
> SP3 (localization + language selection) is done & merged. SP1 (superadmin
> cabinet) follows.

**Goal:** a bot owner/admin can delete their own tenant bot, from both the
master-bot owner console (Telegram) and the HTTP Admin API. Deletion is a
**soft delete** that retains data but releases the unique namespace, so the same
slug and the same Telegram bot can be re-onboarded later without collisions.

## Scope

- **In scope:** delete only. "Stop" already exists as Pause/Resume
  (`set_tenant_status`) in both the owner console and the Admin API — no change.
- **Soft delete** (status `archived`), **one-way** for the owner (no
  self-service restore; a platform admin can recover via DB if ever needed).
- Exposed in **both** surfaces, sharing one domain function (parity with pause).
- Confirmation: **type the slug** (Telegram) / `confirm_slug` body field (HTTP).

## Problem & key decision

`Tenant.slug` is `UNIQUE`; `TenantBot.bot_telegram_id` is `UNIQUE` (nullable);
`TenantBot.webhook_secret_path` is `UNIQUE` (randomized per provisioning).
`bot_username` is not unique.

A naïve soft delete (just set `status="archived"`, keep the row intact) would
**break re-creation**: re-onboarding the same slug, or re-attaching the same
Telegram bot, hits the `slug` / `bot_telegram_id` unique constraints. The fix is
the standard soft-delete pattern — **tombstone the unique fields on delete** so
the namespace is freed while the data stays archived.

## Decisions (from brainstorming)

- Delete = soft delete (`archived`) + tombstone unique fields.
- One-way for the owner; platform-admin recovery is manual/out of scope.
- Both surfaces (owner console + HTTP API), one shared domain function.
- Confirmation guard: type-the-slug / `confirm_slug`.
- Authorization: `owner|admin` (parity with pause; matches "creator/admin").

## Architecture

### What "tombstone" does (single transaction)

In `archive_tenant`:
- `Tenant.status = "archived"`.
- `Tenant.slug = f"{slug}__del{tenant_id}"` — frees the original slug. `tenant_id`
  (the PK) guarantees the tombstone itself is unique.
- For every `TenantBot` of the tenant: `bot_telegram_id = None` (frees the
  Telegram bot for re-attachment) and `status = "archived"`.
- `webhook_secret_path` left as-is (randomized per creation → never collides).
- `bot_token_enc` / `bot_username` retained (audit/history).
- **Idempotent:** if the tenant is already `archived`, no-op (return as-is) — the
  slug is not re-tombstoned.

Result: a later fresh onboarding can reuse the original slug **and** re-attach the
same Telegram bot with zero unique-constraint violations. (Re-onboarding still
needs a fresh invite — existing flow, unaffected, and the subject of SP1.)

### Components / units

**1. Domain — `archive_tenant` (new, `src/quantuum/domain/tenants.py`)**
```python
async def archive_tenant(session, tenant_id: int) -> Tenant | None:
    """Soft-delete a tenant: archive + tombstone its unique fields.

    Frees `slug` and each bot's `bot_telegram_id` so the same slug/bot can be
    re-onboarded later. Idempotent. Returns the tenant, or None if not found.
    Caller records audit + commits (mirrors set_tenant_status usage).
    """
```
Sits beside `set_tenant_status`. Does status flip + tombstoning + `flush()`. The
caller (route / handler) records the audit entry and commits, exactly as the
pause/transfer call sites do.

**2. Owner-console list filter (`src/quantuum/domain/owner_console.py`)**
Add `Tenant.status != "archived"` to the `managed_tenants` query so deleted bots
disappear from `/tenants` and can't be re-managed. (`resolve_managed_tenant_by_slug`
naturally stops resolving the old slug once it's tombstoned.)

**3. Telegram — master-bot owner console (`src/quantuum/bot/handlers/owner_console.py`)**
- Add a `🗑 Delete` button to the `/manage <slug>` keyboard
  (`OwnerManageCb(action="delete", tenant_id=…)` — reuse the existing callback).
- New FSM group `OwnerDelete(awaiting_confirm)` (mirrors `OwnerTransfer`):
  - `delete` callback → `authorize_tenant_action(roles=("owner","admin"))`;
    block the platform tenant; set state `awaiting_confirm` with
    `{tenant_id, slug}`; prompt `owner.delete.prompt` (shows the slug to type).
  - `/cancel` in that state → clear + `owner.delete.cancelled`.
  - text handler in `awaiting_confirm`: if typed text != stored slug →
    `owner.delete.mismatch` (stay in state); else re-authorize, `archive_tenant`,
    `record_audit(action="tenant.delete")`, commit, clear, `owner.delete.done`.

**4. HTTP — `POST /admin/tenants/{tenant_id}/delete` (`src/quantuum/api/routes/admin_tenants.py`)**
Mirrors `pause_tenant`:
- `account = Depends(require_tenant_role(("owner","admin")))`.
- Body `TenantDeleteIn{ confirm_slug: str }` (new schema in `api/schemas.py`).
- Load tenant+bot; `404` if missing.
- `400` if `tenant.is_platform` ("cannot delete the platform tenant").
- `400` if `body.confirm_slug != tenant.slug` ("confirm_slug does not match")
  — validated **before** tombstoning.
- `archive_tenant(session, tenant_id)`; `record_audit(action="tenant.delete")`;
  commit; refresh; return `TenantDetailOut` (slug now tombstoned, status
  `archived`).

**5. i18n (master-bot strings, `src/quantuum/i18n/seed_strings.py`)**
New `{ru,en}` keys (insert-only auto-seed): `owner.manage.kb.delete`,
`owner.delete.prompt` (var `{slug}`), `owner.delete.mismatch`,
`owner.delete.done`, `owner.delete.cancelled`, `owner.delete.platform_blocked`
(dedicated, delete-worded — not reusing the pause key). Reuse the existing
`owner.no_rights` for authorization failures.

## Data flow

```
Owner: /manage mybot → [🗑 Delete]
  → authorize(owner|admin) + platform guard
  → prompt "type `mybot` to confirm"
  → owner types "mybot"  (mismatch → re-prompt; /cancel → abort)
  → archive_tenant: status=archived, slug→mybot__del42, bot_telegram_id→NULL
  → audit tenant.delete; commit
  → reconciler drops the now-non-active bot from the poll pool (next cycle)
  → /tenants no longer lists it

Later: owner gets a fresh invite → onboards slug "mybot", attaches the same
  Telegram bot → no unique collision (slug + bot id were freed). ✅
```

Bot teardown uses the **same path as pause**: `load_active_bot_specs` filters
`status=="active"`, so the archived bot leaves the desired set and the
polling/webhook reconciler cancels its task on the next reconcile cycle
(interval or reload signal). Routing already ignores non-active bots
(`resolve_tenant_id_by_bot` filters `status=="active"`).

## Error handling

- Unknown tenant → `404` (HTTP) / not resolvable (Telegram, slug won't match).
- Platform tenant → blocked in both surfaces.
- Slug mismatch → no deletion; HTTP `400`, Telegram re-prompt.
- Already archived → `archive_tenant` is a no-op; archived tenants aren't listed
  for the owner, so this is effectively unreachable from the UI.
- Lost authorization between request and confirm (Telegram) → re-authorized at
  apply time (mirrors transfer); abort if no longer permitted.
- In-flight arq tasks for a just-archived tenant may still run but deliver via a
  bot that is being torn down — rare, accepted (same window pause has today).

## Deployment note (i18n is insert-only)

New `owner.delete.*` / `owner.manage.kb.delete` keys auto-seed on startup. No
existing key text is changed, so no live `UPDATE` / `invalidate_i18n_all()` is
required. (Ref: the i18n-seed-insert-only gotcha.)

## Testing

Tests run against the test PG/redis (172.30.0.2/.3).

- **Domain `archive_tenant`:** sets `status=archived`, tombstones `slug`
  (`__del{id}`), nulls every bot's `bot_telegram_id`, sets bot `status=archived`;
  idempotent on a second call.
- **Re-creation safety (the core concern, explicit):** archive a tenant, then
  insert a new `Tenant` with the *original* slug **and** a `TenantBot` with the
  *same* `bot_telegram_id` → commits with no `IntegrityError`.
- **`managed_tenants` excludes archived** tenants.
- **Owner console:** `🗑 Delete` button rendered on `/manage`; slug-match →
  archived + audit; slug-mismatch → no change, re-prompt; `/cancel` → aborts;
  platform tenant blocked; unauthorized user blocked.
- **HTTP `POST /{id}/delete`:** `confirm_slug` match → archived + audit +
  `TenantDetailOut`; mismatch → `400`, unchanged; platform → `400`; missing →
  `404`; role enforcement (owner|admin allowed; others rejected).
