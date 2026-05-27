# Tenant-Level Feature Toggle — Design

**Date:** 2026-05-27
**Scope:** SP2 of the platform-plumbing feature wave (content-moderation → **tenant-feature-toggle** → white-label → referrals → gifts → tarot).
**Goal:** Per-tenant on/off control for each of the bot's 12 user-facing surfaces. Owners self-serve via `/owner_console`. Disabled features are hidden from the menu *and* rejected at the handler entry point.

---

## 1. Scope and non-goals

**In scope.** Twelve boolean feature flags per tenant, owner-managed, with menu hiding plus handler gating.

**Out of scope.**
- Per-feature config (model overrides, prompt overrides, max-length, etc.) — deferred to SP6.
- Per-feature pricing / cost-unit overrides — deferred to SP6 (Tarot/I-Ching wave).
- Output moderation, white-label themes, referrals, gifts — separate SPs.
- Superadmin "feature cap" two-tier model — explicitly rejected during brainstorming; tenant owners get full self-serve.

---

## 2. The 12 features

| Flag key | Surface |
|---|---|
| `qa` | `/ask` and the free-text QA handler |
| `blueprint` | "Разбор" / Generate (composite Blueprint reading) |
| `transits` | Transit report |
| `daily` | Daily horoscope |
| `reading.bazi` | Bazi standalone |
| `reading.numerology` | Numerology standalone |
| `reading.human_design` | Human Design standalone |
| `reading.astrology` | Western astrology standalone |
| `reading.vedic` | Vedic standalone |
| `reading.gene_keys` | Gene Keys standalone |
| `reading.mayan` | Mayan standalone |
| `reading.aspects` | Aspects standalone |

The reading kinds are derived from the canonical tuple `READING_KINDS` in `src/quantuum/bot/ui/keyboards.py`.

The top-level "Readings" menu button is *not* a feature flag — its visibility is derived: if at least one `reading.*` flag is on, the Readings button shows; otherwise it is hidden.

Profile, History, Help, Language are not features — they are always on. Owner console, Buy, Onboarding are infrastructure and not flag-gated.

---

## 3. Storage

Reuse the existing `tenant_config` table (model: `TenantConfig` in `src/quantuum/db/models.py:452`). No new table, no Alembic migration.

```
TenantConfig
├── tenant_id  (PK)
├── key        (PK)                 — "feature.<flag-key>" (e.g. "feature.qa", "feature.reading.bazi")
├── value_jsonb                     — {"enabled": false} or {"enabled": true}
├── updated_at
└── updated_by_account_id
```

**Resolution rule.** *Absent row ⇒ feature is ON.* A row exists only when an owner has explicitly overridden the default. Setting a feature back to enabled either writes `{"enabled": true}` or deletes the row — the resolver treats both as ON, so either is safe. The plan will pick "write `{"enabled": true}`" for predictability and audit trail.

Rationale:
- New tenants get everything on by default with zero rows, no seed migration.
- Each row write is atomic and single-purpose.
- Lookup for a single flag is one indexed PK query.
- List-all-flags-for-tenant is one `SELECT WHERE tenant_id = ? AND key LIKE 'feature.%'`.

---

## 4. Domain layer

New module `src/quantuum/domain/tenant_features.py`:

```python
FEATURE_KEYS: tuple[str, ...] = (
    "qa", "blueprint", "transits", "daily",
    "reading.bazi", "reading.numerology", "reading.human_design",
    "reading.astrology", "reading.vedic", "reading.gene_keys",
    "reading.mayan", "reading.aspects",
)

async def is_feature_enabled(session, tenant_id: int, key: str) -> bool: ...
async def list_feature_states(session, tenant_id: int) -> dict[str, bool]: ...
async def set_feature_enabled(
    session, *, tenant_id: int, key: str, enabled: bool, by_account_id: int,
) -> None: ...
```

- `is_feature_enabled` — single-flag lookup; missing row → True, present row → row's `enabled` value.
- `list_feature_states` — returns all 12 keys with their resolved booleans (used by menu builder and owner console).
- `set_feature_enabled` — upserts the row, sets `updated_by_account_id` and `updated_at`, invalidates the per-tenant cache.

Validation: `key not in FEATURE_KEYS` raises `ValueError`. Defensive against typos in handler code.

**Caching.** Follow the existing `cache_aside_async` pattern already used by `domain/tenant_languages.py` — TTL ~60s, keyed by `tenant_id`, holds the full `dict[str, bool]` of 12 flags. `set_feature_enabled` invalidates the entry for that tenant. `is_feature_enabled` reads from `list_feature_states` cache to keep the cache surface small (one entry per tenant covers all 12 flags).

---

## 5. Handler gating (defense-in-depth)

Two layers, both required:

### 5.1 Menu builder hides buttons

`bot/ui/keyboards.py::main_menu_kb` (the reply keyboard) takes a `tenant_id` and the resolved flag dict, and emits only the buttons whose flag is True. The Readings inline keyboard (`readings_menu_kb`) likewise filters `READING_KINDS` against the flag dict before building buttons.

If the resolved set produces an empty Readings menu, the top-level "Readings" button is also omitted.

### 5.2 Handler entry-point check

Each of the 5 entry-point handlers gains an early guard:

```python
async with get_sessionmaker()() as session:
    if not await is_feature_enabled(session, account.tenant_id, "qa"):
        await message.answer(await i18n("feature.disabled_generic"))
        return
```

The 5 entry points and their flag keys:

| Handler | Flag |
|---|---|
| `bot/handlers/qa.py::_submit` | `qa` |
| `bot/handlers/generate.py::on_generate` (or equivalent entry) | `blueprint` |
| `bot/handlers/transits.py` entry | `transits` |
| `bot/handlers/daily.py` entry | `daily` |
| `bot/handlers/readings.py::on_reading_choice` | `reading.<kind>` (resolved from `kind` arg) |

The check fires *before* moderation (`qa`), quota consumption, profile lookup, and enqueue. This means a disabled feature costs nothing in DB writes, LLM calls, or quota.

**Why two layers?** Menu hiding handles ~all real users. Handler gating handles stale buttons cached in old clients, fabricated callback queries, and `/ask`/`/generate` slash commands typed directly. Defense-in-depth.

---

## 6. Owner console UX

Extend `bot/handlers/owner_console.py`. The existing owner main keyboard gains a "Features" entry.

Layout of the Features submenu (inline keyboard):

```
⚙️ Features
[ ✅ QA          ] [ ❌ Blueprint   ]
[ ✅ Transits    ] [ ✅ Daily       ]
── Readings ──
[ ✅ Bazi        ] [ ✅ Numerology  ]
[ ✅ Human Des.  ] [ ❌ Astrology   ]
[ ✅ Vedic       ] [ ✅ Gene Keys   ]
[ ✅ Mayan       ] [ ✅ Aspects     ]
[ ⬅ Back                          ]
```

- `✅` / `❌` prefix reflects current state.
- Tapping a button calls `set_feature_enabled` with `not current_state`, then re-renders the same keyboard with the new state.
- Permission: the existing `owner` role check that already guards `/owner_console`. Non-owners receive the existing "not authorized" response.

New callback class:

```python
class OwnerFeatureCb(CallbackData, prefix="ownerfeat"):
    action: str   # "toggle" | "back"
    key: str      # FEATURE_KEYS member, or "" for back
```

---

## 7. i18n

New keys, 10 languages:

| Key | Type | Where used |
|---|---|---|
| `feature.disabled_generic` | message | Handler gate response (`"This feature isn't available on this bot."`) |
| `owner.features.title` | message | Features submenu title |
| `owner.features.btn` | message | "Features" button label on owner main keyboard |
| `owner.features.section.readings` | message | Subsection divider in features submenu |
| `owner.features.label.qa` | message | "QA" button label |
| `owner.features.label.blueprint` | message | "Blueprint" button label |
| `owner.features.label.transits` | message | "Transits" button label |
| `owner.features.label.daily` | message | "Daily" button label |

Reading-kind labels reuse the existing `readings.kind.<kind>` keys (already seeded in 10 languages).

Per `[[i18n-seed-insert-only]]`: these are all new keys, so they auto-seed on next startup. Russian + English go in `BASE_STRINGS` (`src/quantuum/i18n/seed_strings.py`); the other 8 languages go in their per-language translation modules.

---

## 8. Telemetry

Structured logs via existing `logging_setup.get_logger`:

- `feature.toggled` — fields: `tenant_id`, `key`, `enabled` (new value), `by_account_id`. Emitted on every successful `set_feature_enabled`.
- `feature.gate_blocked` — fields: `tenant_id`, `account_id`, `key`, `surface` (handler name). Emitted when a handler gate rejects a request. INFO level (this is a normal product event, not an error).

No external alerting in this SP. No analytics dashboard — out of scope.

---

## 9. Testing

### 9.1 Domain unit (`tests/test_tenant_features_domain.py`)
- `is_feature_enabled` returns True for an unknown tenant (missing row).
- After `set_feature_enabled(enabled=False)`, returns False.
- After `set_feature_enabled(enabled=True)`, returns True.
- `list_feature_states` returns exactly 12 keys with correct booleans, mixing defaults and overrides.
- `set_feature_enabled(key="not.a.real.key")` raises ValueError.
- `set_feature_enabled` populates `updated_by_account_id` and bumps `updated_at`.
- Cache invalidation: toggle, re-read same session, see new value (cache invalidated by setter).

### 9.2 Handler gate (`tests/test_tenant_features_handlers.py`)
- Disable `qa` → `_submit` returns the `feature.disabled_generic` message; no QA row created; no quota deducted; no `moderation_events` row.
- Disable `reading.bazi` → `on_reading_choice(kind="bazi")` short-circuits; no reading row, no quota, no enqueue.
- Disable `transits` / `daily` / `blueprint` each verified similarly with one test apiece.
- Enabled (default) flags allow the existing flow to run.

### 9.3 Menu (`tests/test_tenant_features_menu.py`)
- `main_menu_kb` with all 12 ON shows the full menu (existing tests should already cover this — verify they still pass).
- With `qa=False` and `daily=False`, those two buttons are absent; Profile / History / Help / Language remain.
- `readings_menu_kb` with `reading.bazi=False` and `reading.vedic=False` shows 6 kinds, omits those 2.
- With all 8 readings off, the readings inline menu would be empty; the top-level "Readings" button is also omitted from the main menu.

### 9.4 Owner console (`tests/test_tenant_features_owner_console.py`)
- Owner sees "Features" button on the owner console keyboard.
- Tapping a feature toggle calls `set_feature_enabled` with the negated state.
- After toggle, the re-rendered keyboard shows the new state (✅ ↔ ❌).
- Non-owner accessing `OwnerFeatureCb(action="toggle", key="qa")` gets the existing "not authorized" response.

### 9.5 i18n (`tests/test_tenant_features_i18n.py`)
- All 8 new keys exist in `BASE_STRINGS` with `ru` and `en` populated.
- All 8 new keys exist in each of the 8 per-language translation modules.

### 9.6 No regressions
- All existing menu / QA / readings / generate / transits / daily tests continue to pass with the gate code in place — they don't touch the feature flags, so the defaults (everything ON) keep them green.

---

## 10. Acceptance criteria

- `domain/tenant_features.py` exposes the three functions with the documented contract.
- A flag stored as `{"enabled": false}` causes both the menu to hide the corresponding button and the handler to short-circuit with the canonical disabled message.
- Owner can toggle any of the 12 flags from `/owner_console → Features`; non-owners cannot.
- Resetting a flag to `enabled=True` restores the feature without restart.
- `feature.toggled` and `feature.gate_blocked` log entries appear with the documented fields.
- All 8 new i18n keys exist in 10 languages.
- Full test suite passes (existing 857 tests + the new suites listed in §9).
