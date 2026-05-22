# Localization fixes + per-user language selection — Design

> Sub-project 3/3 of the management/i18n feature wave (build order 3 → 2 → 1).
> Customer-facing tenant bots only. The master bot (owner onboarding / owner console)
> is already i18n-driven and is out of scope here.

**Goal:** every customer-facing string respects the user's language; a user picks
their language on first `/start` and can change it later from the main menu.

## Problem

Two concrete localization bugs found in the codebase:

1. **`handlers/onboarding.py` is fully hardcoded in Russian** — it is the *only*
   customer-facing handler with zero i18n. Every other handler already uses the
   `i18n: Translator` injected by `AccountMiddleware`. A new English-speaking user
   gets a fully Russian first-touch experience.
2. **Four `or "ru"` fallbacks** hardcode Russian instead of falling back to the
   *tenant's* default language: `tasks/daily.py:65`, `tasks/transits.py:53`,
   `api/routes/me.py:223`, `api/routes/me.py:302`.

And one missing capability: there is **no per-user language selection UI**. The
plumbing already exists — `Account.preferred_lang` (nullable) is honored by
`resolve_lang()` / `Translator.build()` / `AccountMiddleware` — but nothing ever
*sets* it, and no picker exists.

## Decisions (from brainstorming)

- Fix **both** bugs (onboarding i18n + tenant-default fallbacks).
- **First entry:** ask explicitly — a language picker is the first thing a brand-new
  user sees on `/start`, before the welcome/menu. The choice is written to
  `Account.preferred_lang`.
- **Change later:** a `🌐 Язык / Language` button in the main reply menu.
- Picker shows the **tenant's enabled languages** (`get_enabled_langs`), labelled
  with **native names** (not translated). Selection writes `Account.preferred_lang`.

## Architecture

The i18n core (`resolver.py`, `cache.py`, `strings.py`) is unchanged — it already
resolves `preferred_lang → tg_language_code → tenant default → "en"` and caches per
`(tenant, lang)`. This sub-project only adds UI that *sets* `preferred_lang`,
localizes the one un-localized handler, and corrects four fallbacks.

### Components / units

**1. Language picker (reusable)**
- New callback factory in `bot/ui/callbacks.py`:
  ```python
  class LangCb(CallbackData, prefix="lang"):
      action: str  # setup | set
      lang: str = ""
  ```
  `action="setup"` = first-entry flow (followed by welcome + menu);
  `action="set"` = menu change (followed by a confirmation + menu re-render).
- New native-label map + keyboard builder in `bot/ui/keyboards.py`:
  ```python
  LANG_LABELS = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}  # native, untranslated

  async def language_picker_kb(tenant_id: int, *, action: str) -> InlineKeyboardMarkup:
      # opens its own session (like Translator.__call__) and reads enabled langs:
      #   async with get_sessionmaker()() as session:
      #       enabled = await get_enabled_langs(session, tenant_id)
      #       default = await get_tenant_default_lang(session, tenant_id)
      # order = default lang first, then remaining enabled langs sorted (deterministic);
      # one inline button per lang, label = LANG_LABELS.get(code, code.upper()),
      # callback_data = LangCb(action=action, lang=code); adjust(1)
  ```
  Native labels keep the picker readable regardless of the current language.
  Handlers pass `tenant_id` (injected by `TenantMiddleware` as `data["tenant_id"]`);
  no `session` is injected into handlers, so the builder owns its session.

**2. Language handler — new `bot/handlers/language.py`**
- `@router.callback_query(LangCb.filter())` → `on_set_language`:
  - persist the choice in a fresh session (the middleware-injected `account` is
    detached after its session closed): `async with get_sessionmaker()() as session:
    acc = await session.get(Account, account.id); acc.preferred_lang =
    callback_data.lang; await session.commit()`,
  - build a fresh `Translator(tenant_id=…, lang=callback_data.lang)` (the
    middleware-injected `i18n` still carries the *old* language),
  - `action == "setup"` → `i18n("start.welcome")` then `show_main_menu(...)`,
  - `action == "set"` → `i18n("lang.changed")` then `show_main_menu(...)`,
  - `query.answer()`.
- Router registered in `bot/app.py` (customer dispatcher) alongside the others.

**3. First-entry gate — `bot/handlers/start.py`**
- `on_start`: if `account.preferred_lang is None`, send `i18n("lang.prompt")` with
  `language_picker_kb(action="setup")` and **return** (no welcome yet). Otherwise the
  current behavior (welcome + menu). `on_start` gains `account: Account` and
  `tenant_id: int` params (both injected by middleware); it calls
  `language_picker_kb(tenant_id, action="setup")`. The picker shows once;
  pre-existing accounts (preferred_lang NULL) see it on their next `/start`.

**4. Menu button — `bot/handlers/menu.py`, `bot/ui/keyboards.py`, `bot/ui/text.py`**
- Add `btn.language` to `MENU_BUTTON_KEYS` (`text.py`) so its label set is derived
  for routing across all enabled languages.
- Render it in `main_menu_kb` (`keyboards.py`); change layout to `adjust(2, 2, 2, 2)`
  (8 buttons).
- New routing handler `@router.message(F.text.in_(_LANGUAGE_LABELS))` → send
  `lang.prompt` + `language_picker_kb(action="set")`.

**5. Localize `bot/handlers/onboarding.py`**
- Inject `i18n: Translator` into every handler (`on_full_name`, `on_birth_date`,
  `on_birth_time`, `on_birth_place_location`, `on_birth_place_text`,
  `on_birth_place_other`, `on_geo_confirm`, `on_geo_retry`, `start_onboarding`,
  and the `_finalize_profile` / `save_collected_profile` helpers as needed).
- Replace hardcoded RU literals with new `onb.*` keys (each `{ru, en}`):
  `onb.prompt.full_name`, `onb.error.full_name`, `onb.prompt.birth_date`,
  `onb.error.birth_date`, `onb.prompt.birth_time`, `onb.error.birth_time`,
  `onb.prompt.birth_place`, `onb.done`.
- For the geocoding confirm/retry sub-flow **reuse the existing** keys
  `profile.place.confirm`, `profile.place.not_found`, `profile.kb.place_confirm`,
  `profile.kb.place_retry` (DRY). This aligns onboarding with the profile flow's
  place-only confirmation (the raw `Часовой пояс: {tz}` line is dropped from the
  "found place" message).
- Build the confirm keyboard via i18n-aware buttons (use the shared
  `profile.kb.place_*` labels) rather than the current hardcoded inline buttons.

**6. Fix the four `or "ru"` fallbacks → tenant default**
Replace `<x> or "ru"` with
`await resolve_lang(session, tenant_id=…, preferred_lang=<x>, tg_language_code=None)`
(already falls back to the tenant default lang, then `"en"`):
- `tasks/daily.py:65` (`lang` used for `claim_horoscope` + delivery),
- `tasks/transits.py:53` (`row.lang` → LLM output language),
- `api/routes/me.py:223` and `:302` (`account.preferred_lang` → LLM output language).
Each call site already has a `session` and a `tenant_id` (or `account.tenant_id`).

## Data flow

```
/start (new user, preferred_lang = NULL)
  → AccountMiddleware builds Translator (tenant default, since preferred_lang NULL)
  → on_start: preferred_lang is None → send lang.prompt + picker(setup)
  → user taps 🇬🇧 English
  → on_set_language: account.preferred_lang = "en"; commit;
       Translator(lang="en") → welcome + menu (English)
  → user taps Profile → Fill profile → onboarding (now English)

Main menu → 🌐 Язык / Language → picker(set) → on_set_language → lang.changed + menu
```

## i18n keys

New platform strings (INSERT-ONLY seed; see "Deployment" below):
- `lang.prompt` — "Выбери язык:" / "Choose your language:"
- `lang.changed` — "Язык изменён." / "Language updated."
- `btn.language` — "🌐 Язык" / "🌐 Language"
- `onb.prompt.full_name`, `onb.error.full_name`
- `onb.prompt.birth_date`, `onb.error.birth_date`
- `onb.prompt.birth_time`, `onb.error.birth_time`
- `onb.prompt.birth_place`
- `onb.done`

Reused (no new rows): `profile.place.confirm`, `profile.place.not_found`,
`profile.kb.place_confirm`, `profile.kb.place_retry`, `start.welcome`, `menu.title`,
`kb.cancel`.

`LANG_LABELS` (native language names) is a code-level constant, **not** an i18n key —
native names are the same in every language and must not be translated.

## Error handling

- Picker only ever offers enabled languages, so `on_set_language` always receives a
  valid `lang`; if `get_enabled_langs` somehow returns empty, the picker degrades to
  the tenant default (handled by the existing resolver) — defensively, ignore a
  `lang` not in enabled and just re-render the menu.
- Onboarding parse errors keep their existing control flow (re-prompt on invalid
  input); only the *text* moves to i18n.
- Fallback fix is behavior-preserving when a tenant's default is `ru` (the common
  case today); it only changes behavior for tenants whose default is not `ru`.

## Deployment note (i18n is insert-only)

`ensure_base_strings` is INSERT-ONLY. New keys (`lang.*`, `btn.language`, `onb.*`)
auto-seed on startup — nothing extra. No existing key text is *changed* here
(onboarding reuses existing `profile.place.*` rows as-is), so no live UPDATE +
`invalidate_i18n_all()` is required for this change. (Ref: the i18n-seed-insert-only
gotcha.)

## Testing

Tests run against the test PG/redis (172.30.0.2/.3); geocoding HTTP is mocked.

- **Start gate:** `on_start` with `preferred_lang=None` sends `lang.prompt` + a picker
  whose buttons carry `LangCb`; with `preferred_lang` set, sends welcome + menu (no
  picker).
- **Picker kb:** `language_picker_kb` lists exactly the tenant's enabled langs with
  native labels and correct `LangCb(action=…, lang=…)`.
- **Set language:** `on_set_language` persists `account.preferred_lang`, and renders
  welcome+menu for `setup` / `lang.changed`+menu for `set`, in the chosen language.
- **Menu button:** a `btn.language` label routes to the picker; `all_menu_labels()`
  includes the new labels.
- **Onboarding localization:** each onboarding prompt/error renders from i18n —
  assert RU (default tenant) and EN values; assert no remaining hardcoded RU literal
  in the handler.
- **Fallback fix:** with `preferred_lang=None` on a tenant whose default lang is
  `en`, the resolved lang is `en` (not `ru`).
- Update `tests/test_bot_start_menu_profile.py` where the menu button-label set is
  asserted (now includes `btn.language`).
```
