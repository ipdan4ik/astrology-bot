# Audit Fix Sweep — Design

Date: 2026-06-03
Status: Approved (design); pending implementation plan

## Background

A six-workstream parallel audit (customer-bot handlers, owner-console, hub/master
bot, domain layer, HTTP API, i18n) surfaced a set of correctness, money-handling,
security, and UX defects. The top findings were verified directly in code. This
document specifies how each will be fixed. Every fix is driven by TDD: a failing
regression test that reproduces the defect, then the fix.

Delivery: one branch `fix/audit-sweep`, ordered commits per workstream, money and
security first, UX last. Order: A → B → D → C → E → F → G.

## Decisions (locked with user)

1. **Credit model:** the `AccountPackage` ledger is the single source of truth;
   `package_credits` becomes a derived cache.
2. **Permissions:** destructive and financial actions are `owner`-only; `admin`
   keeps read + day-to-day ops (feature toggles, branding, stats, customer view).
3. **UX depth:** full owner-console + hub-bot navigation refactor.
4. **Security scope:** webhook secret-token + idempotency, refresh-token rotation,
   and input-validation hardening are all in scope.

### Default sub-decisions (may be revised)

- Welcome and referral credits: **no expiry**. Gift credits keep their existing expiry.
- `AccountBalance.free_trial_used` column stays (logic removed, no schema churn).
- Manual owner deduct drains the ledger FIFO (mirror of consume).
- Referral double-attribution is prevented with an app-level row lock, **not** by
  re-adding the dropped `uq_start_token_uses_account_id` (that table is shared with
  gift tokens; a blanket unique would break gift claims).

## Workstream A — Credit ledger as single source of truth

The crux. Today `consume_quota` (`domain/quota.py:60`) comments that the
`package_credits` counter is the source of truth, while
`recompute_account_balance` (`domain/billing.py:85`) overwrites that counter from
`SUM(AccountPackage.requests_remaining)`. Gifts, referral payouts, and welcome
credits write only the counter, so the next payment-triggered recompute silently
erases them.

### Schema migration

- `account_packages.plan_id` → **nullable** (gifts/referrals/welcome have no plan).
- Add `account_packages.source TEXT NOT NULL DEFAULT 'purchase'`
  (`purchase | gift | referral | welcome | manual | backfill`).
- **Backfill:** for each `AccountBalance` where `package_credits` exceeds
  `SUM` of its valid (non-expired, `requests_remaining > 0`) ledger rows, insert one
  compensating `AccountPackage` row for the difference: `source='backfill'`,
  `expires_at=NULL`, `plan_id=NULL`, `requests_remaining=diff`. This protects
  existing counter-only balances from being zeroed by the first recompute after deploy.

### Code

- New helper `grant_credits(session, *, account_id, tenant_id, amount, source,
  expires_at=None, payment_id=None, plan_id=None)`: always INSERTs a ledger row,
  then sets `package_credits = SUM(valid ledger rows)`. The **single entry point**
  for every credit addition.
- Rewire all counter-only writes through it:
  - welcome credits — `auth/identity.py:18`
  - gift redemption — `bot/handlers/start_tokens.py:155`
  - gift sweep-refund — `domain/gifts.py:257` (also add `bal is None` guard)
  - referral payout — `domain/referrals.py:208`
  - manual owner grant — `bot/handlers/owner_users.py:219`
- Manual **deduct** (negative owner adjustment): drain ledger FIFO + recompute,
  not a bare counter decrement.
- `consume_quota`: drain ledger FIFO, then set `package_credits` from the ledger;
  remove the "counter is source of truth / packages best-effort" fallback. Remove
  the **dead `free_trial` branch** (`quota.py:47`) — welcome credits replaced the
  one-shot trial.
- **Atomicity:** `refund_quota` locks the `Request` row (`with_for_update`) to
  prevent double-refund. Reading handlers (`qa`, `readings`, `transits`,
  `generate`, `divination`) wrap charge → create → enqueue and call `refund_quota`
  on any post-charge failure.
- **Bug #2 (divination):** move the natal-profile check *before* `consume_quota`
  in `_perform_draw_and_enqueue` (`bot/handlers/divination.py:161,170`).

### Tests

Backfill correctness; gift/referral/welcome credits survive a subsequent payment
recompute; consume drains ledger and syncs counter; refund is idempotent under
concurrent calls; divination on missing profile does not charge.

## Workstream B — Referral integrity

- **Double payout:** make `maybe_payout_referral` idempotent with
  `UPDATE start_token_uses SET claimed_at=now() WHERE id=:id AND claimed_at IS NULL`
  and gate the payout on rowcount == 1. `claimed_at` already exists for this purpose.
- **Double attribution:** `SELECT ... FOR UPDATE` the account row before the
  read-then-insert in `handle_referral_token` (`bot/handlers/start_tokens.py:81`).
- **Tenant scoping:** scope the "has any paid payment" check in
  `maybe_payout_referral` (`domain/referrals.py:194`) by `token.tenant_id`; add the
  same `tenant_id` filter to the dedup lookup in `apply_subscription_payment`
  (`domain/billing.py:111`, audit #H3).

### Tests

Concurrent `/start <ref>` clicks produce at most one attribution and one payout;
a paid payment in another tenant does not trigger payout.

## Workstream C — Hub-bot onboarding

- **Token uniqueness/ownership (#5):** `finalize_provisioning`
  (`domain/provisioning.py`) rejects a token whose `bot_telegram_id` is already an
  active `TenantBot`. New domain error surfaced by the handler as a new i18n key
  `master.onboard.token_in_use` (added in all 10 languages). Wrap `get_me()` in
  `asyncio.wait_for`.
- **Invite consumption (#6):** move `invite.used_count += 1` from
  `create_tenant_from_onboarding` to `finalize_provisioning` (consume on success,
  not on start). Guard against the same invite spawning a second un-finalized tenant.

### Tests

Duplicate bot token is rejected; an abandoned onboarding leaves the invite usable.

## Workstream D — Permissions & tenant scoping

- Pass `roles=("owner",)` to `authorize_tenant_action` for: delete, pause/resume,
  confirm-delete (`bot/handlers/owner_console.py`), and grant/ban/unban
  (`bot/handlers/owner_users.py`). API: restrict plan pricing, balance grant, and
  ban to `owner`.
- **Cross-tenant ban (#8):** ban/unban handlers call `get_customer_card` (which
  validates `acc.tenant_id == tenant_id`) before mutating the account.
- **IDOR (#11):** scope `get_subscription_plan` / `get_package_plan`
  (`domain/plans.py:30`) by `tenant_id IS NULL OR == account.tenant_id`; 404 otherwise.
- **#13:** `find_superadmin_by_tg` (`auth/identity.py:73`) uses `.first()`.
- Management endpoints (`api/deps.py:require_tenant_role`) and webhook delivery
  (`domain/tenants.py:86`) reject `archived`/`suspended` tenants by joining
  `Tenant.status`.

### Tests

Admin cannot delete/pause or grant credits; owner can. Ban with a cross-tenant
account_id is rejected. Cross-tenant plan_id returns 404. Suspended tenant cannot
hit management endpoints and its bot stops receiving updates.

## Workstream E — API security hardening

- **Webhook (#9, #10):** register the Telegram webhook with a per-bot
  `secret_token`; verify the `X-Telegram-Bot-Api-Secret-Token` header in
  `api/routes/webhook.py` before enqueueing. Deduplicate `(bot_telegram_id,
  update_id)` via Redis `SETNX` (short TTL) to drop replays.
- **Refresh-token rotation (#12):** `/auth/refresh` revokes the consumed refresh
  token and issues a new one; reuse of an already-consumed token revokes the chain.
- **Input validation:** Pydantic `Field(ge=, le=)` on `BalancePatchIn.package_credits`,
  plan `price_cents`/`period_days`/`request_count`, `NatalProfileIn.latitude/longitude`,
  `InviteCreateIn.max_uses`; `Query(ge=1, le=200)` pagination caps on `me.py` list
  endpoints and pagination added to the currently-unbounded ones.

### Tests

Webhook rejects missing/wrong secret and duplicate update_id; refresh rotates and
detects reuse; out-of-range inputs are rejected with 422.

## Workstream F — Owner-console + hub-bot UX refactor

- **Dead Transfer button:** add an `OwnerManageCb(action="transfer")` callback
  handler that owner-authorizes and drives the existing transfer FSM
  (`bot/handlers/owner_console.py:158`).
- **Navigation:** consistent `‹ Back` row + `edit_text` in-place navigation across
  every submenu (Features, Branding, Referrals, Gifts, Stats, Users). Add a
  manage-menu re-render callback so submenus can return.
- **Features keyboard:** regroup so core features are one block and reading types a
  separate block.
- **Missing toggles (#14):** add Referrals and Gifts toggle buttons to the features
  keyboard.
- **Hub bot:** Back/Edit steps in onboarding, cancel keyboard on every prompt,
  `/cancel` handler covering all onboarding FSM states, `ReplyKeyboardRemove` on
  cancel and manual-token paths.
- **i18n:** move hardcoded Russian strings in `tasks/provision.py:15` into the
  Translator.

### Tests

Transfer button enters the FSM; every submenu has a working Back; referrals/gifts
toggles flip state; provisioning prompts resolve via i18n.

## Workstream G — i18n & misc cleanup

- Migration that force-UPDATEs the recently-renamed keys (Blueprint rename,
  `help.text`, `btn.generate`) into live `platform_strings` and calls
  `invalidate_i18n_all()` — the seeder is insert-only and will not otherwise update
  changed text.
- `bot/handlers/history.py:38-39`: localize reading status via `status_label` and
  interpolate through i18n `safe_format` (drop raw `str.format()`); add `default=`
  to the dynamic `readings.kind.{kind}` lookup.
- `set_horoscope_status` / `set_reading_status` / `set_qa_status` /
  blueprint status: allowlist the `**fields` keys against model columns.
- `mark_payment_paid` (`domain/billing.py:52`): guard `payment is None`.
- Payout idempotency: `calculate_payout` checks `find_payout_for_period` (or a
  unique constraint on `(tenant_id, period_start, period_end)`) before inserting.

### Tests

Renamed keys reach a seeded DB; history renders localized status without crashing
on a stray brace; unknown status field raises; duplicate payout period is rejected.

## Out of scope (follow-ups)

- JWT `iss`/`aud` binding and `options.require` hardening (audit #M1).
- Magic-link rate limiting / HTTPS enforcement (audit #M4).
- DST edge cases in daily-horoscope scheduling (audit #M4 domain).
- Synchronous ephemeris compute in arq workers (existing accepted tradeoff).
