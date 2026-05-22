# Master-bot superadmin cabinet — Design

> Sub-project 1/3 of the management/i18n feature wave (build order 3 → 2 → 1).
> SP3 (i18n) and SP2 (tenant-bot deletion) are done & merged. This is the last.

**Goal:** a platform superadmin can, from inside the MASTER bot via Telegram,
view and manage all tenant bots (list, stats, suspend/resume, delete) and manage
tenant invites (create, list, revoke) — through a **button-driven** cabinet.
Today these are HTTP-Admin-API-only.

## Problem: the superadmin Telegram-identity gap

`Account.is_superadmin` is a boolean; superadmins have `tenant_id=None` and only a
`magic_link` (email) identity (seeded from `BOOTSTRAP_SUPERADMIN_EMAIL`). The master
bot's `AccountMiddleware` resolves the messaging user via a **tenant-scoped**
`find_or_create_account_by_tg(tenant_id=platform_id, tg_user_id=…)`, which cannot
match a `tenant_id=None` superadmin account — it just creates a plain
platform-scoped account with `is_superadmin=False`. So a superadmin DMing the
master bot is invisible as a superadmin. `AccountIdentity` has **no** unique
constraint on `(provider, provider_user_id)` (only an index), so a superadmin can
hold a `tg_chat` identity that coexists with the middleware-created platform one.

## Decisions (from brainstorming)

- **Identity bridge:** env-linked Telegram id at bootstrap (`BOOTSTRAP_SUPERADMIN_TG_ID`).
- **Manage scope:** list all tenants + stats + suspend/resume + delete (cross-tenant).
- **Invite scope:** create (one-tap default) + list + revoke.
- **UI:** button-driven — a single `/admin` entry opens an inline menu; all
  navigation/actions are inline keyboards.
- **Entry command:** `/admin`. **Non-superadmins:** terse denial (consistent with
  the master bot's other commands, which reply rather than stay silent).

## Architecture

The HTTP superadmin surface (`/admin/platform/*`) is unchanged. SP1 adds a
Telegram cabinet that **reuses the existing domain functions** and adds the missing
identity resolution. No new tables; one new nullable-friendly identity row per
superadmin (created at bootstrap).

### Identity bridge

- **Setting** `bootstrap_superadmin_tg_id: str | None` (env `BOOTSTRAP_SUPERADMIN_TG_ID`).
- **Bootstrap** (`db/bootstrap.py:ensure_superadmin`): after ensuring the superadmin
  account by email, if the tg id is set, idempotently attach
  `AccountIdentity(account_id=<superadmin>, provider="tg_chat", provider_user_id=<tg id>)`
  (skip if it already exists on that account).
- **Resolver** (`auth/identity.py`): new
  `find_superadmin_by_tg(session, tg_user_id) -> Account | None` — join
  `AccountIdentity(provider="tg_chat", provider_user_id=tg) → Account` where
  `Account.is_superadmin == True`. The `is_superadmin` filter ignores the duplicate
  platform-scoped identity, so it returns exactly the superadmin account (or None).
- **Authorization:** every cabinet handler calls `find_superadmin_by_tg(str(from_user.id))`
  (NOT the middleware-injected `account`). None → denial. The returned superadmin
  account is the audit actor.

### Cabinet UI (button-driven) — `bot/handlers/master_superadmin.py` (new)

Entry: `@router.message(Command("admin"))` → authorize → inline menu.
All other steps are `@router.callback_query(SuperAdminCb.filter(...))`.

```
/admin → [🏢 Tenants] [🎟 Invites]

🏢 Tenants → one button per non-archived tenant ("{display_name} — {status}")
            + [⬅️ Back]
   tap tenant → manage screen:
        [📊 Stats]
        [⏸ Suspend] or [▶️ Resume]   (depending on status)
        [🗑 Delete]
        [⬅️ Tenants]
     • Stats   → tenant_stats(...) text
     • Suspend → set_tenant_status(id, "suspended", "paused") + audit, re-render
     • Resume  → set_tenant_status(id, "active", "active") + audit, re-render
     • Delete  → type-the-slug confirm (FSM, reuses the SP2 pattern) →
                 archive_tenant(id) + audit

🎟 Invites → one row per active invite ("{code} · {tier} · {used}/{max}")
             each with [🗑 Revoke]; + [➕ New invite] + [⬅️ Back]
     • New invite → create_invite(default: basic, max_uses=1, no expiry,
                    created_by=<superadmin>) → reply with the deep-link
                    https://t.me/<MASTER_BOT_USERNAME>?start=<code>
     • Revoke     → revoke_invite(id) + audit, re-render
```

### New callback — `bot/ui/callbacks.py`

```python
class SuperAdminCb(CallbackData, prefix="sa"):
    action: str  # menu | tenants | tenant | suspend | resume | delete | invites | newinvite | revoke
    tenant_id: int = 0
    invite_id: int = 0
```

### Reused / new domain helpers

- Reuse: `set_tenant_status`, `archive_tenant`, `tenant_stats`, `create_invite`,
  `list_invites`, `revoke_invite`.
- New small helper `list_all_tenants(session)` in `domain/tenants.py` — non-archived,
  non-platform, ordered by id (the cabinet's tenant list). (The platform tenant is
  excluded so it can't be suspended/deleted.)

### i18n (master-bot strings, `i18n/seed_strings.py`)

New `admin.*` `{ru,en}` keys (insert-only auto-seed): the menu title + button
labels, the tenants/invites list headers + empty states, the manage-screen labels,
the invite-created message (with the deep-link), revoke confirmation, and the
non-superadmin denial. The type-the-slug delete sub-flow **reuses the existing SP2
`owner.delete.prompt` / `owner.delete.mismatch` / `owner.delete.done` /
`owner.delete.cancelled`** keys (same semantics, DRY); `owner.delete.platform_blocked`
is not needed (the platform tenant is excluded from the list). Exact key list is
enumerated in the plan.

### Audit

`record_audit` with the superadmin account as `actor_account_id`:
- tenant actions → `tenant.pause` / `tenant.resume` / `tenant.delete` (target
  `tenant_id`) — same action names the SP2 owner console uses, so audit queries stay
  consistent across both surfaces;
- invite actions → `platform.invite.create` / `platform.invite.revoke`
  (mirroring the existing HTTP platform routes; `tenant_id=None`).

## Data flow

```
superadmin DMs master bot /admin
  → AccountMiddleware injects a platform-scoped account (is_superadmin=False) [ignored]
  → handler: find_superadmin_by_tg(tg) → superadmin account (is_superadmin=True)
  → inline menu
  → 🏢 Tenants → list_all_tenants → buttons → tap → manage screen
       → Suspend/Resume/Delete → reuse domain fn + audit (actor=superadmin)
       → teardown of a suspended/deleted bot via the existing reconciler (status≠active)
  → 🎟 Invites → list_invites → New invite → create_invite → deep-link reply
       → Revoke → revoke_invite + audit
```

## Error handling

- Non-superadmin runs `/admin` or a `SuperAdminCb` callback → terse denial; cabinet
  not rendered.
- Stale callback (tenant/invite no longer exists or already archived/revoked) →
  re-render the list with a short notice (no crash).
- Platform tenant excluded from `list_all_tenants` → cannot be suspended/deleted.
- Delete uses type-the-slug confirm + re-authorization at apply time (mirrors SP2).
- `BOOTSTRAP_SUPERADMIN_TG_ID` unset → no tg identity linked; the cabinet simply has
  no Telegram-authorized superadmin (HTTP still works). Setting it later links on the
  next startup (idempotent).

## Deployment note (i18n is insert-only)

New `admin.*` keys auto-seed on startup; no existing key text changes, so no live
`UPDATE` / `invalidate_i18n_all()` is needed. (Ref: the i18n-seed-insert-only gotcha.)
`BOOTSTRAP_SUPERADMIN_TG_ID` must be set in the (gitignored) env for the operator's
Telegram id; the linkage is applied at the next worker/runner startup.

## Testing

Tests run against the test PG/redis (172.30.0.2/.3); fake Message/CallbackQuery +
monkeypatched `get_sessionmaker` (the established master-bot handler test pattern).

- **Identity:** `find_superadmin_by_tg` returns the superadmin account, ignoring a
  coexisting platform-scoped `tg_chat` identity for the same id; returns None for a
  non-superadmin tg id. Bootstrap linking is idempotent (no duplicate identity on a
  second startup).
- **Gate:** `/admin` by a superadmin shows the menu; by a non-superadmin → denial,
  no menu.
- **Tenants:** list excludes archived + platform tenants; stats renders; suspend then
  resume flips `Tenant.status`/`TenantBot.status` + writes audit; delete via
  type-the-slug archives + tombstones + audit; slug-mismatch does not archive.
- **Invites:** new-invite creates an invite + replies with a deep-link containing the
  code; list shows active invites; revoke sets status revoked + audit.
- **Authz on callbacks:** a non-superadmin firing a `SuperAdminCb` callback is denied
  (no mutation, no audit).
