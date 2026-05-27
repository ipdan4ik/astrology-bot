# SP4: Referral Links — Design Spec

**Date:** 2026-05-27
**Status:** Approved (brainstorm)
**Related:** SP1 content-moderation, SP2 tenant-feature-toggle, SP3 white-label branding (all merged on local main).

## Goal

Let existing tenant-bot customers share a Telegram deep link that brings new
users to the same tenant bot, attributes the new user to the sharer, and
rewards the sharer with package credits once the new user has both paid and
spent at least one credit. The deep-link layer is built to be reused for
future code types (discount, promo) without rework.

## Non-goals

- Multi-level / chain referrals (no second-degree payouts).
- Claw-back on refund (out of scope for v1; documented).
- Code regeneration / rotation for personal referral codes (one stable code
  per account in v1).
- Public leaderboards / gamification.

## Reward model (locked)

- **Trigger:** referee has at least one `Payment` row with `status='paid'`
  *and* has just successfully consumed `>=1` `package_credit` (i.e.
  `consume_quota` returned `"package"`). Both conditions evaluated at the
  end of `consume_quota` on the referee's account; order between
  payment and spend is irrelevant — the first post-payment package spend
  fires the payout.
- **Reward recipient:** referrer only (one-sided).
- **Reward amount:** `referral_reward_credits` (per-tenant config, default
  **10**, range 0–1000 enforced in owner UI). If set to 0 the payout is
  suppressed but the use row is still marked claimed (closes the loop so it
  cannot retrigger later).
- **One-shot per referee:** `UNIQUE(account_id)` on `start_token_uses`
  guarantees a referee can be attributed at most once.

## Token layer (generic; SP4 only seeds kind='referral')

### `start_tokens`

| column             | type           | notes                                                                 |
| ------------------ | -------------- | --------------------------------------------------------------------- |
| `code`             | text **PK**    | 8-char base32, opaque, globally unique across tenants                 |
| `kind`             | text           | `referral` for SP4 (future: `discount`, `promo`, ...)                 |
| `tenant_id`        | int FK         | scopes resolution                                                     |
| `owner_account_id` | int FK, NULL   | referrer for kind=`referral`; NULL for tenant-owned codes             |
| `payload`          | JSONB          | empty for SP4 (kind-specific data later)                              |
| `status`           | text           | `active` / `disabled`                                                 |
| `max_uses`         | int NULL       | NULL = unlimited (personal referral default)                          |
| `used_count`       | int            | bumped per successful use                                             |
| `expires_at`       | timestamptz NULL | NULL = never                                                        |
| `created_at`       | timestamptz    |                                                                       |

Indexes: PK on `code`; `(tenant_id, kind)`; `(owner_account_id)` for stat
lookups.

### `start_token_uses`

| column        | type             | notes                                                       |
| ------------- | ---------------- | ----------------------------------------------------------- |
| `id`          | int PK           |                                                             |
| `token_code`  | text FK          | -> `start_tokens.code`                                      |
| `account_id`  | int FK, **UNIQUE** | enforces one-token-per-account                            |
| `used_at`     | timestamptz      | when `/start <code>` was redeemed                           |
| `claimed_at`  | timestamptz NULL | when referral payout fired (NULL = pending)                 |

Index: `(token_code, claimed_at)` for stats; `(account_id)` is unique.

## Deep-link dispatcher

`/start <payload>` (existing handler at `src/quantuum/bot/handlers/start.py`)
parses the payload. New flow:

```
on_start(message):
  payload = parse_start_payload(message.text)   # whitespace after /start
  if payload:
    token = await resolve_start_token(session, code=payload, tenant_id=tenant_id)
    if token is None:
      send i18n("invite.unknown_code"); continue normal /start flow
    else:
      await dispatch_start_token(token, account=account, session=session)
  # then existing welcome / language-picker flow runs as today
```

`dispatch_start_token` looks up a handler by `token.kind`. SP4 registers
exactly one handler: `referral`. Unknown kinds log a warning and fall
through silently (defensive — older codes from a future kind shouldn't
crash older bot builds).

### `referral` handler

```
async def handle_referral_token(token, *, account, session):
  if token.owner_account_id == account.id:
    return                                          # self-referral: silent
  if token.status != "active": return
  if token.expires_at and token.expires_at <= utcnow(): return
  if token.max_uses is not None and token.used_count >= token.max_uses: return
  try:
    session.add(StartTokenUse(token_code=token.code, account_id=account.id,
                              used_at=utcnow()))
    token.used_count += 1
    await session.flush()
  except IntegrityError:
    return                                          # already attributed: silent
  await write_audit(session, kind="referral.attributed",
                    payload={"referee_id": account.id,
                             "referrer_id": token.owner_account_id,
                             "code": token.code})
```

## Payout site (referral domain layer)

New module `src/quantuum/domain/referrals.py`:

- `generate_referral_code(session, *, account_id, tenant_id) -> str` —
  lazy-creates a `start_tokens` row with kind=`referral`,
  `max_uses=NULL`, `expires_at=NULL`. Idempotent: returns existing code if
  account already has one. 8-char base32, collision-retry up to 5x then
  raise. Writes `AuditLog` event `referral.code_created`.
- `get_referral_stats(session, *, account_id) -> {claimed: int, code: str | None}`
  — count of claimed uses for the account's code, plus current code.
- `maybe_payout_referral(session, *, referee_account_id) -> bool` —
  invoked at the end of `consume_quota` when `charged_against == "package"`.
  Checks: unclaimed use row exists; `EXISTS Payment(status='paid')` for
  referee; reads `referral.reward_credits` from `TenantConfig` (default 10);
  if >0, `adjust_package_credits(referrer, +N)` then `claimed_at=utcnow()`;
  if 0, just `claimed_at=utcnow()`. Writes `AuditLog`
  `referral.payout`. Wrapped in try/except by the caller — payout failure
  must NOT roll back the spend.
- `get_reward_credits(session, tenant_id) -> int` / `set_reward_credits(session, *, tenant_id, value, by_account_id)`
  — TenantConfig key `referral.reward_credits`, integer 0–1000.

### Integration with `consume_quota`

Patch `src/quantuum/domain/quota.py::consume_quota` so that after the
existing `await session.commit()` on the `"package"` branch returns, we call
`maybe_payout_referral(session, referee_account_id=account_id)` inside a
nested try/except (log + swallow). The payout writes are committed in a
separate flush within the same domain helper so the spend is durable
regardless of payout outcome.

## Customer UX — `/invite` + main menu button

- New module `src/quantuum/bot/handlers/invite.py`:
  - `/invite` command handler.
  - Callback handler for new main-menu button `menu.invite`.
- Main menu (`bot/handlers/menu.py::show_main_menu`): add new button
  "Invite a friend" (i18n key `menu.invite`) row above Profile/Language.
  Button is *omitted* when `is_feature_enabled(tenant_id, "referrals")` is
  False (per SP2 patterns).
- `show_invite(message, account, tenant_id, i18n)`:
  1. Lazy-generate referral code via `generate_referral_code`.
  2. Fetch bot username from `TenantBot` for this tenant.
  3. Fetch stats via `get_referral_stats`.
  4. Render i18n template `invite.title` / `invite.link_label` /
     `invite.earned` with vars `link`, `earned`, `friends`.
  5. Show a "Share" inline button as a `url` button pointing to
     `https://t.me/share/url?url=<encoded_link>&text=<encoded_share_text>`.
     Telegram's native share sheet opens — works for any tenant bot
     regardless of inline-mode setting.

When tenant-feature `referrals` is disabled, `/invite` replies with
`invite.disabled` text (no keyboard, no link generation).

## Owner UX — `/owner_console`

- Extend SP2 `FEATURE_KEYS` with `"referrals"` (13 total, default-ON). The
  existing Features submenu and toggle keyboard pick up the new key with
  zero code changes beyond the constant + i18n label.
- New "Referrals" button in `/owner_console` main keyboard (sibling to
  Features and Branding). Opens a submenu showing:
  ```
  <i18n: owner.referrals.title>
  <i18n: owner.referrals.current_value>: 10

  [Edit reward]   [Reset to default]
  ```
- Edit FSM (mirrors SP3 Branding pattern): state `awaiting_value`, user
  sends integer, validate 0–1000, save via `set_reward_credits`. `/cancel`
  exits state. `/reset` deletes the override row.
- AuditLog: `referral.config_set` (tenant, old, new, by_account).

## i18n keys (16 new; ru/en seeded explicitly, 8-locale fallback per SP3)

| key                                | purpose                                            |
| ---------------------------------- | -------------------------------------------------- |
| `menu.invite`                      | Main menu button label                             |
| `invite.title`                     | Invite screen title                                |
| `invite.link_label`                | "Your link:" label                                 |
| `invite.earned`                    | "Earned: {credits} from {friends} friends"        |
| `invite.share_text`                | Prefilled text for the Share button                |
| `invite.disabled`                  | Shown when tenant-feature `referrals` is off       |
| `invite.unknown_code`              | `/start <bad-code>` user-facing message            |
| `owner.referrals.title`            | Owner submenu title                                |
| `owner.referrals.current_value`    | "Current reward: {value} credits"                  |
| `owner.referrals.prompt`           | "Send an integer 0-1000 to set the reward"         |
| `owner.referrals.saved`            | "Reward set to {value}"                            |
| `owner.referrals.reset`            | "Reward reset to default ({value})"                |
| `owner.referrals.too_large`        | "Value must be between 0 and 1000"                 |
| `owner.referrals.not_a_number`     | "Send a number"                                    |
| `owner.referrals.cancel_hint`      | "Send /cancel to abort"                            |
| `owner.referrals.menu_button`      | "Referrals" label on /owner_console main keyboard  |

Placeholder convention follows SP3: `{language}` reserved name, all other
template vars free.

## AuditLog events

- `referral.code_created` — account_id, tenant_id, code
- `referral.attributed` — referee_id, referrer_id, code (written by
  dispatcher on successful use)
- `referral.payout` — referee_id, referrer_id, amount, code
- `referral.config_set` — tenant_id, old_value, new_value, by_account_id

## File / module plan

New files:
- `src/quantuum/db/models.py` — append `StartToken`, `StartTokenUse`.
- `migrations/versions/<rev>_start_tokens.py` — Alembic for both tables.
- `src/quantuum/domain/referrals.py` — generate / stats / payout /
  config getters and setters.
- `src/quantuum/bot/handlers/start_tokens.py` — dispatcher + `referral`
  handler.
- `src/quantuum/bot/handlers/invite.py` — `/invite` + menu callback.

Edited files:
- `src/quantuum/db/models.py` — new tables.
- `src/quantuum/i18n/seed_strings.py` — 16 new keys ru/en.
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — same 16 per locale.
- `src/quantuum/domain/quota.py` — call `maybe_payout_referral` after
  successful `"package"` consumption.
- `src/quantuum/domain/tenant_features.py` — add `"referrals"` to
  `FEATURE_KEYS`.
- `src/quantuum/bot/handlers/start.py` — parse payload, dispatch token
  before existing welcome flow.
- `src/quantuum/bot/handlers/menu.py` — add Invite button (feature-gated).
- `src/quantuum/bot/handlers/owner_console.py` — Referrals button +
  submenu + FSM (mirrors SP3 Branding shape).
- `src/quantuum/bot/ui/callbacks.py` — add `OwnerReferralsCb` CallbackData.

Test files (new):
- `tests/test_referral_domain.py` — generator, idempotency, stats,
  `maybe_payout_referral` happy + edge cases.
- `tests/test_start_token_dispatcher.py` — payload parsing, unknown code,
  expired/disabled/maxed, self-referral, already-attributed.
- `tests/test_referral_i18n.py` — all 16 keys seeded in 10 locales.
- `tests/test_invite_handler.py` — /invite command, menu button, disabled
  case, share button rendering, stats numbers.
- `tests/test_owner_referrals.py` — submenu, FSM edit, validation, reset,
  AuditLog write.
- `tests/test_consume_quota_referral_integration.py` — end-to-end:
  payment + spend -> payout fires; spend without payment -> no payout;
  second spend -> no double payout.

## Security & abuse posture

- **Self-referral** blocked by code-level check.
- **One-token-per-account** enforced by `UNIQUE(account_id)` on
  `start_token_uses`.
- **Sockpuppet farms** mitigated by the trigger gating on real payment.
  A bad actor must successfully purchase Stars on a fresh referee account
  to extract a single payout — economically negative for the attacker at
  any reasonable reward setting; no further day-one cap needed.
- **Code enumeration** mitigated by 8-char base32 codes (~10^12 keyspace,
  read-only lookup, no rate limit needed at expected scale; can add later
  if abuse appears).
- **Refund / chargeback** — out of scope for v1; we do not claw back
  paid-out credits. Documented limitation; revisit if support volume
  warrants.

## Out-of-scope deferred

- Configurable reward per *kind* (referral vs promo). SP4 hardcodes
  referral. Promo/discount kinds will introduce their own configuration
  surface when they ship.
- Per-referrer monthly cap.
- Reward both sides (referee bonus). Reward model is locked to
  referrer-only.
- Multi-tier / chain referrals.

## Acceptance criteria

1. `start_tokens` + `start_token_uses` tables exist with correct columns
   and constraints; Alembic migration runs clean both ways.
2. Generic dispatcher in `/start` correctly routes by `kind`, falls
   through to existing welcome flow when no payload or unknown code (the
   latter also surfaces `invite.unknown_code`).
3. Customer can run `/invite` or tap the menu button, sees their link,
   share button, and accurate earned stats.
4. Self-referral / already-attributed silently no-op.
5. `consume_quota` triggers `maybe_payout_referral` only on `"package"`
   spend; payout fires only when referee has a paid Payment row; payout
   marks `claimed_at` and is one-shot per referee.
6. Owner can change reward via `/owner_console` Referrals submenu;
   default 10; range 0–1000; reset works; AuditLog records the change.
7. Tenant feature flag `referrals` (SP2) hides the menu button and
   disables `/invite` cleanly when toggled off.
8. All 16 i18n keys present in 10 locales; existing i18n tests pass.
9. Full test suite green; ruff clean on touched source files.
