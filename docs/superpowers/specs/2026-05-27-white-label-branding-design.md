# White-Label Branding — Design

**Date:** 2026-05-27
**Scope:** SP3 of the platform-plumbing feature wave (content-moderation → tenant-feature-toggle → **white-label-branding** → referrals → gifts → tarot).
**Goal:** Per-tenant override of four brand-identity surfaces — display name, welcome message, help text, and a new long-form output signature. Owners self-serve via `/owner_console`. Per-language opt-in.

---

## 1. Scope and non-goals

**In scope.** Four brandable surfaces:

1. `display_name` — Tenant column, single value (no `lang`).
2. `start.welcome` — i18n key, per-language override.
3. `help.text` — i18n key, per-language override.
4. `brand.signature` — **new** i18n key, per-language override, appended to long-form LLM outputs.

**Out of scope.**
- LLM tone / personality / preset themes — deferred to SP6 (Tarot wave or later).
- Cover images, stickers, profile pictures — no media-send surfaces exist today.
- Full free-form override of all 227 i18n keys — too much UI for too little benefit.
- Telegram-side bot name (BotFather field) — not controllable from our code.
- Output moderation of owner-written branding text — owner is a trusted role.

---

## 2. Storage

Reuse two existing tables. No new tables, no Alembic migration.

### 2.1 `Tenant.display_name`

Existing column (`src/quantuum/db/models.py:17-37`). Single value, not language-scoped. Plain UPDATE via ORM.

### 2.2 `TenantStringOverride`

Existing table (`src/quantuum/db/models.py:468-476`):

```
TenantStringOverride
├── tenant_id  (PK)
├── key        (PK)            — e.g. "start.welcome", "help.text", "brand.signature"
├── lang       (PK)            — ISO 639-1 code, e.g. "ru", "en"
├── text                       — the override value
├── updated_at
└── updated_by_account_id
```

The existing resolver in `src/quantuum/i18n/strings.py:15-25` already merges `PlatformString` (base) with `TenantStringOverride` (per-tenant) — overrides win. Zero new resolver work.

**Resolution rule.** *Absent row ⇒ platform default.* A row exists only when an owner has explicitly customized that key + language.

### 2.3 New base key: `brand.signature`

Seeded in `src/quantuum/i18n/seed_strings.py` with `text = ""` (empty string) in all 10 languages. Per `[[i18n-seed-insert-only]]`, this is a new key, so insert-on-startup applies automatically.

---

## 3. Domain layer

New module `src/quantuum/domain/tenant_branding.py`:

```python
BRANDING_I18N_KEYS: tuple[str, ...] = (
    "start.welcome",
    "help.text",
    "brand.signature",
)

MAX_DISPLAY_NAME_LEN = 64
MAX_WELCOME_LEN = 2000
MAX_HELP_LEN = 2000
MAX_SIGNATURE_LEN = 200


async def get_branding_text(
    session, *, tenant_id: int, key: str, lang: str
) -> str | None:
    """Return owner override for (tenant, key, lang), or None if not overridden."""
    ...


async def set_branding_text(
    session,
    *,
    tenant_id: int,
    key: str,
    lang: str,
    text: str,
    by_account_id: int,
) -> None:
    """Upsert TenantStringOverride row. Validates key in BRANDING_I18N_KEYS and length."""
    ...


async def reset_branding_text(
    session, *, tenant_id: int, key: str, lang: str
) -> None:
    """Delete TenantStringOverride row → fall back to platform default."""
    ...


async def set_display_name(
    session, *, tenant_id: int, display_name: str, by_account_id: int
) -> None:
    """Update Tenant.display_name. Validates length and no newlines."""
    ...
```

Validation:
- `key not in BRANDING_I18N_KEYS` → `ValueError`.
- `len(text)` outside per-key bound → `ValueError`.
- `display_name` containing `\n` or `\r` → `ValueError`.
- Empty `display_name` → `ValueError` (must be 1-64).
- Empty `brand.signature` value: callers should use `reset_branding_text` instead of `set_branding_text(text="")`. Setter raises `ValueError` on `text == ""` to force the API distinction.

---

## 4. brand.signature rendering

The signature is appended at the **output rendering layer**, not in the LLM system prompt. This keeps the LLM oblivious to per-tenant branding and avoids prompt-injection surface.

### 4.1 Where it appears

Long-form LLM outputs only:

| Surface | Render site |
|---|---|
| Blueprint (composite) | After the deterministic stitcher in `src/quantuum/llm/blueprint_writer.py` (or the worker step that finalizes the message) |
| Each of 8 standalone readings | After the per-kind worker finalizes the message |
| Daily horoscope | After `daily` worker finalizes |
| Transit report | After `transits` worker finalizes |
| QA answer | After QA worker finalizes |

**Not** applied to: menus, errors, confirmations, onboarding prompts, owner-console UX, history listings, moderation responses.

### 4.2 How it's appended

Helper in `src/quantuum/bot/rendering/signature.py`:

```python
async def append_signature(body: str, *, tenant_id: int, lang: str) -> str:
    """Append brand.signature on a new line. No-op if the resolved string is empty."""
    translator = await build_translator(tenant_id=tenant_id, lang=lang)
    sig = (await translator("brand.signature")).strip()
    if not sig:
        return body
    return f"{body}\n\n{sig}"
```

The helper uses the existing Translator factory (whatever builds `Translator` instances elsewhere in handlers — `build_translator` is a placeholder for the actual factory name). The Translator goes through the existing `i18n/strings.py` resolver: platform base + tenant override merger. Platform default for `brand.signature` is `""` → no-op when nobody has overridden. No extra newlines when empty.

Worker integration points: each finalizer calls `append_signature(text, tenant_id=..., lang=...)` before invoking `deliver_via_tenant_bot`.

### 4.3 Per-language behavior

The resolver returns the override for the user's language if one exists, else the platform default (`""`). Owners who customize signature only in `ru` get the signature in Russian-language messages and no signature in messages going to English-speaking users.

---

## 5. Owner console UX

### 5.1 Entry point

`bot/handlers/owner_console.py::on_manage` keyboard gains a "Branding" button next to "Features":

```
[ ⚙️ Features ]
[ 🎨 Branding ]
[ ⬅ Back     ]
```

### 5.2 Branding submenu

```
🎨 Branding (lang: ru)
[ Name: "Quantuum Bot"            ]
[ Welcome: "Привет! Я помогу…"    ]
[ Help: "Этот бот делает…"        ]
[ Signature: (пусто)              ]
[ ⬅ Back                          ]
```

- Each entry shows current value (Tenant.display_name for the name; resolved value for the three i18n keys) truncated to ~40 characters with a `…` ellipsis.
- The `(lang: ru)` header reflects the owner's *current* `i18n.lang`. Switching language (existing `/language`) lets the owner edit overrides for that language.
- Tap → FSM transition (new `BrandingEditState`) to "awaiting_value" for that key. Bot replies:

  > "Send the new text for **Welcome (ru)**, or `/cancel` to keep current. Send `/reset` to clear the override and fall back to the platform default."

- Owner sends text → validate → upsert `TenantStringOverride` (or update `Tenant.display_name`) → re-render submenu with new preview.
- `/reset` → call `reset_branding_text` (no-op for display_name; that surface has no reset since it's a column, not an override).
- Validation errors reply with the specific reason (`"too long: 2150 chars (max 2000)"`).

### 5.3 New callback class

```python
class OwnerBrandingCb(CallbackData, prefix="obrand"):
    action: str       # "open" | "edit"
    tenant_id: int
    key: str          # "display_name" | "start.welcome" | "help.text" | "brand.signature" | "" (for back/open)
```

### 5.4 Authorization

Existing `authorize_tenant_action(actor, tenant_id)` guard. Non-owners attempting `OwnerBrandingCb` get the existing "not authorized" response.

---

## 6. i18n

One new key:

| Key | Type | Where used |
|---|---|---|
| `brand.signature` | message | Long-form output footer (rendering helper) |

Plus three new keys for the owner UX:

| Key | Type | Where used |
|---|---|---|
| `owner.branding.btn` | message | "Branding" button label on /manage |
| `owner.branding.title` | message | Submenu title `🎨 Branding (lang: {lang})` — uses `{lang}` placeholder |
| `owner.branding.label.name` | message | "Name" entry label |
| `owner.branding.label.welcome` | message | "Welcome" entry label |
| `owner.branding.label.help` | message | "Help" entry label |
| `owner.branding.label.signature` | message | "Signature" entry label |
| `owner.branding.prompt` | message | FSM prompt: "Send the new text for **{label}** ({lang}), or /cancel… /reset…" |
| `owner.branding.saved` | message | Confirmation: "✅ Updated." |
| `owner.branding.reset_done` | message | Confirmation: "↩️ Reset to default." |
| `owner.branding.cancelled` | message | "Cancelled." |
| `owner.branding.too_long` | message | Validation error: "Too long: {actual} chars (max {limit})." |
| `owner.branding.bad_format` | message | "Display name must be 1-64 chars and contain no newlines." |
| `owner.branding.empty_value` | message | "Empty value not allowed. Use /reset to clear an override." |
| `owner.branding.preview_empty` | message | "(empty)" placeholder shown in preview when override absent and default empty |

All keys seeded in `BASE_STRINGS` (ru + en) and in the 8 per-language translation modules.

---

## 7. Telemetry

Structured logs via `logging_setup.get_logger("tenant_branding")`:

- `branding.updated` — fields: `tenant_id`, `key` (`"display_name"` or one of the three i18n keys), `lang` (or `null` for display_name), `by_account_id`, `length` (character count of the new value, not the value itself). INFO-level.
- `branding.reset` — fields: `tenant_id`, `key`, `lang`, `by_account_id`. INFO-level.

No external alerting. No analytics dashboard.

---

## 8. Testing

### 8.1 Domain unit (`tests/test_tenant_branding_domain.py`)

- `set_branding_text` upserts row for `(tenant, key, lang)`.
- `set_branding_text` validates `key in BRANDING_I18N_KEYS` (raises ValueError on unknown).
- `set_branding_text` validates per-key length bound.
- `set_branding_text(text="")` raises ValueError (force callers to use reset).
- `get_branding_text` returns the override when row exists.
- `get_branding_text` returns None when row absent.
- `reset_branding_text` deletes the row (idempotent on absent row — no-op, no error).
- `set_display_name` updates Tenant.display_name and bumps `updated_at` (if such field exists; otherwise just sets).
- `set_display_name` validates length and rejects newlines.
- `set_display_name` rejects empty string.

### 8.2 Owner console (`tests/test_tenant_branding_owner_console.py`)

- "Branding" button appears in `/manage` keyboard for the tenant owner.
- Non-owner pressing `OwnerBrandingCb(action="open", ...)` gets "not authorized".
- Submenu shows current values truncated.
- Submenu header reflects owner's current `i18n.lang`.
- Tapping "Welcome" transitions to FSM `awaiting_value`; subsequent text upserts override for owner's current lang and re-renders submenu.
- `/cancel` exits FSM, keeps current value.
- `/reset` calls `reset_branding_text` and re-renders.
- Value over the per-key limit returns `owner.branding.too_long` with `{actual}` and `{limit}` filled.
- Display name with `\n` returns `owner.branding.bad_format`.
- Override is scoped to current lang: edit while `lang=ru`, then switch to `lang=en` — English users see platform default (no row in `en`).

### 8.3 Signature rendering (`tests/test_brand_signature_integration.py`)

- Empty override (platform default `""`) → `append_signature` returns body unchanged (no trailing newlines).
- Non-empty override → appended as `body + "\n\n" + signature`.
- Whitespace-only override is treated as empty (no append).
- Signature renders in QA answer worker output.
- Signature renders in blueprint composite output.
- Signature renders in each of the 8 standalone reading outputs (parametrized).
- Signature renders in daily output.
- Signature renders in transit output.
- Signature does NOT render in menu / error / onboarding / owner UX responses.
- Per-lang routing: tenant has override for `ru` only; user with `lang=ru` sees signature; user with `lang=en` does not.

### 8.4 i18n (`tests/test_tenant_branding_i18n.py`)

- `brand.signature` exists in `BASE_STRINGS` with `ru=""` and `en=""`.
- `brand.signature` exists in all 8 per-language translation modules with default `""`.
- All `owner.branding.*` keys exist in `BASE_STRINGS` with `ru` and `en` populated.
- All `owner.branding.*` keys exist in all 8 per-language translation modules.

### 8.5 No regressions

- All existing /start, /help, blueprint, reading, daily, transit, QA tests continue to pass with the rendering helper in place — they don't set overrides, so default empty signature means zero output change.

---

## 9. Acceptance criteria

- `domain/tenant_branding.py` exposes `get_branding_text`, `set_branding_text`, `reset_branding_text`, `set_display_name` with documented contracts.
- Owner can edit display_name, welcome, help, signature from `/manage → Branding`; non-owners cannot.
- Editing welcome / help / signature creates a `TenantStringOverride` row for owner's current `i18n.lang`. Other languages remain on platform default.
- `brand.signature` is seeded as empty string in 10 languages; absent override → no footer rendered, no trailing newlines.
- Non-empty signature appears in QA, blueprint, all 8 standalone readings, daily, transit outputs — and nowhere else.
- `branding.updated` and `branding.reset` log entries appear with documented fields (length, not content).
- All 15 new i18n keys exist in 10 languages (`brand.signature` + 14 `owner.branding.*`).
- Full test suite passes (existing 964 tests + the new suites listed in §8).
