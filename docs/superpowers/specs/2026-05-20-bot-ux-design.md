# Bot UX (buttons, profile, history) — Design

**Status:** Draft (post-brainstorm), awaiting plan
**Date:** 2026-05-20
**Builds on:** Plan 1 (Foundation MVP) + `feat/local-polling` (long-polling entrypoint, onboarding round-trip/timezone fix)

## 1. Overview

A convenience UX layer on top of the existing command-driven aiogram3 bot: a persistent reply-keyboard main menu, a profile screen with per-field editing, a paginated generation-history browser, and an immediate "generate" action. Existing commands (`/start`, `/profile`, `/blueprint`) remain as aliases. Pure-Russian text (i18n is deferred to platform Plan 5).

### Goals
- Persistent main menu (reply keyboard): `🔮 Разбор · 👤 Профиль · 📜 История · ℹ️ Помощь`.
- Profile screen: view stored natal data; edit individual fields without re-running the whole onboarding.
- History screen: paginated list of past Blueprints → detail with re-download + preview.
- Generate action that mirrors `/blueprint` (gate on profile + quota → enqueue), triggered immediately on tap.
- Inline navigation (pagination, field-edit, cancel) via typed `CallbackData`.

### Non-goals
- i18n / multi-language (platform Plan 5 — text hardcoded RU here).
- "Тарифы"/payment screens (platform Plan 3).
- Profile deletion, inline-mode, settings screen.
- Multi-tenant resolution (still single default tenant).

## 2. Approach (chosen)

Dedicated `bot/ui/` package of **pure functions** (keyboard builders, `CallbackData` factories, text formatters, paging) + one thin handler module per screen. Existing command handlers become aliases delegating to the same screen functions. Pure functions are unit-tested directly; handlers stay thin.

## 3. File structure

```
src/quantuum/bot/
  ui/
    __init__.py
    keyboards.py    # main_menu_kb(); profile_kb(has_profile); history_list_kb(entries, page, has_next);
                    #   blueprint_detail_kb(bp_id, can_download); cancel_kb()
    callbacks.py    # CallbackData: ProfileCb, HistoryCb, BlueprintCb, OnboardCb
    text.py         # render_profile(profile); render_history_entry(bp); render_detail(bp);
                    #   MENU_LABELS; HELP_TEXT
    paging.py       # page_slice(items, page, size) -> (slice, has_next)   [pure]
  handlers/
    menu.py         # show_main_menu(message); reply-button routing; ℹ️ Помощь
    profile.py      # profile view screen + per-field edit FSM (ProfileEdit)
    history.py      # history list + pagination + detail
    generate.py     # 🔮 Разбор button + /blueprint command + request_blueprint_for_account (moved here)
    start.py        # /start -> show_main_menu
    onboarding.py   # existing 6-step full FSM (entry: "Заполнить профиль" / /profile fallback)
  app.py            # register routers (menu, profile, history, generate, onboarding, start) + RedisStorage
```

`bot/handlers/blueprint.py` is removed: its `request_blueprint_for_account` helper and the `/blueprint` command move into `generate.py` (avoids two routers binding `/blueprint`). Tests referencing `quantuum.bot.handlers.blueprint` move to `generate`.

## 4. Screens & navigation

**Main menu** — reply keyboard, always visible. Labels (exact strings, matched by text filter): `🔮 Разбор`, `👤 Профиль`, `📜 История`, `ℹ️ Помощь`.

**/start** → greeting + `main_menu_kb()`.

**Profile** (`👤 Профиль` / `/profile`):
- Profile exists → `render_profile()` text + `profile_kb(has_profile=True)`: inline field buttons `Имя · Дата · Время · Место · Координаты · Таймзона`.
- No profile → "Профиль не заполнен" + `profile_kb(has_profile=False)`: `[Заполнить профиль]` → starts full onboarding FSM (`onboarding.py`).
- Field edit: tap field button → `ProfileCb(action="edit", field=...)` → prompt for that field + `cancel_kb()`; user replies → validate via existing parser; on success load current profile, replace the one field, `upsert_natal_profile(...all fields...)`, re-show profile; on invalid → re-prompt.

**Generate** (`🔮 Разбор` / `/blueprint`): immediate. `request_blueprint_for_account(...)` gate → `no_profile` → message + `[Заполнить профиль]`; `no_quota` → trial-used message; `queued` → "Генерирую твой разбор, ~1 минута…". Delivery handled by task-worker (Plan 1).

**History** (`📜 История`):
- Query account's blueprints `ORDER BY id DESC`, `LIMIT size+1 OFFSET page*size`; `page_slice` computes the page + `has_next`. Page size = 5.
- `history_list_kb`: one button per entry `🔮 <DD.MM> · <status_ru>` → `HistoryCb(action="open", bp_id=...)`; pager row `[← Пред]`(`HistoryCb(action="page", page=p-1)`) / `[След →]`(`page=p+1`) shown conditionally.
- Empty → "Пока нет генераций" + `[🔮 Сгенерировать]`.
- Detail (`HistoryCb open`): ownership check (`bp.account_id == account.id`, else ignore/answer); `render_detail()` (status, created/completed); `blueprint_detail_kb(bp_id, can_download=bool(llm_md))`: `[📥 Скачать .md]`(`BlueprintCb download`) sends `BufferedInputFile(llm_md)`, `[👁 Превью]`(`BlueprintCb preview`) sends first 500 chars, `[← Назад]`(`BlueprintCb back`) → back to current list page.

**Help** (`ℹ️ Помощь`): static `HELP_TEXT` — what the bot does, command list, support contact placeholder.

## 5. Keyboards & callbacks

- Reply menu matched by exact text via aiogram `F.text == LABEL` filters. The literal-string coupling lives only in `menu.py`/`text.py`; Plan 5 swaps these for `t()` keys.
- `CallbackData` factories (aiogram 3 `CallbackData` subclasses, prefix per type):
  - `ProfileCb(action: str, field: str = "")` — `action ∈ {edit}` (field ∈ name|birth_date|birth_time|birth_place|coords|timezone)
  - `HistoryCb(action: str, page: int = 0, bp_id: int = 0)` — `action ∈ {page, open}`
  - `BlueprintCb(action: str, bp_id: int)` — `action ∈ {download, preview, back}`
  - `OnboardCb(action: str)` — `action ∈ {start, cancel}` (the "Заполнить профиль" button everywhere uses `OnboardCb(action="start")`)
- Every FSM branch (full onboarding + per-field edit) includes `cancel_kb()` (`OnboardCb(action="cancel")`) → clears state, returns to the originating screen.

## 6. Per-field profile edit

- `ProfileEdit` FSM: a single state `awaiting_value`; `editing_field` stored in FSM data.
- One message handler reads `editing_field`, validates with the matching helper (`parse_birth_date`, `parse_birth_time`, `parse_coords`, `is_valid_timezone`, or plain text for name/place), re-prompts on invalid.
- On valid: `get_natal_profile(account.id)` → build full kwargs from existing profile overriding the one field → `upsert_natal_profile(...)` → clear state → re-render profile screen.
- Editing requires an existing profile (entry buttons only shown when profile exists).

## 7. FSM storage

`create_dispatcher` uses `RedisStorage.from_url(settings.redis_url)` instead of `MemoryStorage`, so onboarding/edit state survives worker restarts and works across multiple workers (Plan 2). Redis is already a dependency.

## 8. Testing

Pure units (no live Telegram):
- `keyboards.py`: builders return expected button labels/structure (e.g. `main_menu_kb` has 4 buttons; `history_list_kb` shows pager only when `has_next`/`page>0`).
- `callbacks.py`: `pack`/`unpack` round-trip for each factory.
- `text.py`: `render_profile`/`render_detail`/`render_history_entry` format known inputs; status→RU mapping.
- `paging.py`: `page_slice` slicing + `has_next` across boundaries.
- profile edit: a pure `apply_field_edit(profile_kwargs, field, raw_value) -> (kwargs|None, error|None)` helper validated per field (so the handler stays thin and the validation logic is unit-tested).

Handlers themselves are thin wrappers; existing integration tests (quota, blueprint create) remain green.

## 9. Integration notes / risks

- **Reply-button text vs commands:** reply taps arrive as normal text messages; the account middleware runs first (injects `account`, `chat_id`), then the `F.text == LABEL` handlers match. Router order: command handlers and menu-text handlers must be registered so a label never shadows free-text FSM input — FSM-state handlers are state-scoped, menu-text handlers are global; aiogram matches state handlers within an active state first. Document expected handler/router ordering in `app.py`.
- **`/blueprint` consolidation:** ensure only `generate.py` binds `/blueprint` after `blueprint.py` removal.
- **RedisStorage availability:** tests need the test Redis (already in conftest); a unit test for `create_dispatcher` should assert it builds with RedisStorage without requiring a live connection at construction time (RedisStorage.from_url is lazy).
- **Pre-i18n literals:** all user-facing strings hardcoded RU in `text.py`/`menu.py`; centralizing them there keeps the Plan 5 i18n migration mechanical.
