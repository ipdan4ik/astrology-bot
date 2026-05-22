# Localization fixes + per-user language selection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every customer-facing string respects the user's language; a user picks their language on first `/start` and can change it from the main menu.

**Architecture:** The i18n core already resolves `preferred_lang → tg_language_code → tenant default → "en"` and is honored by `AccountMiddleware`. This plan only adds UI that *sets* `Account.preferred_lang` (a picker), localizes the one un-localized handler (`onboarding.py`), and replaces four hardcoded `or "ru"` fallbacks with tenant-default resolution. No DB migration, no i18n core change.

**Tech Stack:** Python 3.12, aiogram 3 (CallbackData, Router, F filters, InlineKeyboardBuilder/ReplyKeyboardBuilder, FSM), SQLModel/asyncpg, Redis, pytest + pytest-asyncio (auto mode).

**Conventions for every task:**
- Tests need the test PG/redis up at `172.30.0.2` / `172.30.0.3` (docker test stack). Geocoding HTTP is always mocked.
- Run only the task's targeted tests during the task; run the full suite once at the end (Task 8).
- Run tests with `uv run pytest …`.
- New i18n keys auto-seed (insert-only) — no live `UPDATE` / `invalidate_i18n_all()` needed for this change.

---

### Task 1: Add the new i18n keys to BASE_STRINGS

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (add keys to the `BASE_STRINGS` dict)
- Test: `tests/test_i18n_seed.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_i18n_seed.py`:

```python
def test_language_selection_strings_present():
    from quantuum.i18n.seed_strings import BASE_STRINGS

    for key in [
        "lang.prompt",
        "lang.changed",
        "btn.language",
        "onb.prompt.full_name",
        "onb.error.full_name",
        "onb.prompt.birth_date",
        "onb.error.birth_date",
        "onb.prompt.birth_time",
        "onb.error.birth_time",
        "onb.prompt.birth_place",
        "onb.done",
    ]:
        assert key in BASE_STRINGS, f"missing {key}"
        assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_i18n_seed.py::test_language_selection_strings_present -v`
Expected: FAIL with `AssertionError: missing lang.prompt`

- [ ] **Step 3: Add the keys**

In `src/quantuum/i18n/seed_strings.py`, insert these entries into the `BASE_STRINGS` dict. Put the `btn.language` entry right after the existing `btn.daily` entry (with the other `btn.*` keys); put the rest in a new section just before the final closing `}` of the dict (after the `owner.transfer.done` entry):

```python
    # Language selection (picker + menu button)
    "btn.language": {
        "ru": "🌐 Язык",
        "en": "🌐 Language",
    },
    "lang.prompt": {
        "ru": "Выбери язык:",
        "en": "Choose your language:",
    },
    "lang.changed": {
        "ru": "Язык изменён.",
        "en": "Language updated.",
    },
    # -------------------------------------------------------------------------
    # Onboarding flow (onboarding.py) — RU values are the exact pre-i18n literals
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": {
        "ru": "Введи полное имя (как в свидетельстве о рождении):",
        "en": "Enter your full name (as on your birth certificate):",
    },
    "onb.error.full_name": {
        "ru": "Не понял имя. Введи полное имя текстом:",
        "en": "Couldn't read the name. Enter your full name as text:",
    },
    "onb.prompt.birth_date": {
        "ru": "Дата рождения в формате ГГГГ-ММ-ДД (например 1980-06-24):",
        "en": "Date of birth in YYYY-MM-DD format (e.g. 1980-06-24):",
    },
    "onb.error.birth_date": {
        "ru": "Не понял дату. Формат ГГГГ-ММ-ДД:",
        "en": "Couldn't read the date. Format YYYY-MM-DD:",
    },
    "onb.prompt.birth_time": {
        "ru": "Время рождения ЧЧ:ММ (например 10:00):",
        "en": "Time of birth HH:MM (e.g. 10:00):",
    },
    "onb.error.birth_time": {
        "ru": "Не понял время. Формат ЧЧ:ММ:",
        "en": "Couldn't read the time. Format HH:MM:",
    },
    "onb.prompt.birth_place": {
        "ru": (
            "Место рождения: пришли геопозицию (📎 → Геопозиция, можно поставить точку "
            "на карте) или напиши город / часть адреса:"
        ),
        "en": (
            "Place of birth: send your location (📎 → Location, you can drop a pin on the "
            "map) or type a city / part of an address:"
        ),
    },
    "onb.done": {
        "ru": "Готово! Профиль сохранён. Команда /blueprint сгенерирует твой разбор.",
        "en": "Done! Your profile is saved. The /blueprint command will generate your reading.",
    },
```

Note: the onboarding place-confirm sub-flow reuses existing keys (`profile.place.confirm`, `profile.place.not_found`, `profile.kb.place_confirm`, `profile.kb.place_retry`, `profile.prompt.birth_place`) — do **not** add new keys for those.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_i18n_seed.py::test_language_selection_strings_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py tests/test_i18n_seed.py
git commit -m "feat(i18n): seed language-selection + onboarding strings"
```

---

### Task 2: LangCb callback + language_picker_kb

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py` (add `LangCb`)
- Modify: `src/quantuum/bot/ui/keyboards.py` (add `LANG_LABELS` + `language_picker_kb`)
- Test: `tests/test_language_picker.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_language_picker.py`:

```python
from quantuum.bot.ui.callbacks import LangCb


def _inline(markup):
    return [b for row in markup.inline_keyboard for b in row]


async def test_picker_lists_enabled_langs_default_first(session, default_tenant):
    # Seed ru (default) + en for the tenant.
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.keyboards import language_picker_kb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()

    markup = await language_picker_kb(default_tenant.id, action="setup")
    buttons = _inline(markup)

    labels = [b.text for b in buttons]
    assert labels == ["🇷🇺 Русский", "🇬🇧 English"]  # default (ru) first, then sorted

    codes = [LangCb.unpack(b.callback_data).lang for b in buttons]
    assert codes == ["ru", "en"]
    actions = {LangCb.unpack(b.callback_data).action for b in buttons}
    assert actions == {"setup"}


async def test_picker_uses_action(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.keyboards import language_picker_kb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()

    markup = await language_picker_kb(default_tenant.id, action="set")
    actions = {LangCb.unpack(b.callback_data).action for b in _inline(markup)}
    assert actions == {"set"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_language_picker.py -v`
Expected: FAIL with `ImportError: cannot import name 'LangCb'`

- [ ] **Step 3a: Add `LangCb` to callbacks.py**

Append to `src/quantuum/bot/ui/callbacks.py`:

```python
class LangCb(CallbackData, prefix="lang"):
    action: str  # setup | set
    lang: str = ""
```

- [ ] **Step 3b: Add `LANG_LABELS` + `language_picker_kb` to keyboards.py**

In `src/quantuum/bot/ui/keyboards.py`, update the imports at the top:

```python
from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, LangCb, OnboardCb, ProfileCb
from quantuum.db.session import get_sessionmaker
from quantuum.i18n import Translator
from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.strings import get_enabled_langs, get_tenant_default_lang
```

Then add, after the `_PROFILE_FIELDS` constant near the top:

```python
# Native language names for the picker. NOT i18n keys — native names are the same
# in every language and must not be translated. Falls back to the uppercased code.
LANG_LABELS = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}
```

And add this function (e.g. after `main_menu_kb`):

```python
async def language_picker_kb(tenant_id: int, *, action: str) -> InlineKeyboardMarkup:
    """Inline picker of the tenant's enabled languages, default lang first.

    Owns its own DB session (no session is injected into handlers). *action* is
    "setup" (first-entry flow) or "set" (menu change), carried in the callback.
    """
    async with get_sessionmaker()() as session:
        enabled = await get_enabled_langs(session, tenant_id)
        default = await get_tenant_default_lang(session, tenant_id)
    if default in enabled:
        ordered = [default, *sorted(c for c in enabled if c != default)]
    else:
        ordered = sorted(enabled)
    b = InlineKeyboardBuilder()
    for code in ordered:
        b.button(
            text=LANG_LABELS.get(code, code.upper()),
            callback_data=LangCb(action=action, lang=code),
        )
    b.adjust(1)
    return b.as_markup()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_language_picker.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/ui/keyboards.py tests/test_language_picker.py
git commit -m "feat(i18n): LangCb + language_picker_kb (native labels, default-first)"
```

---

### Task 3: Language handler (set preferred_lang)

**Files:**
- Create: `src/quantuum/bot/handlers/language.py`
- Modify: `src/quantuum/bot/app.py` (register the router)
- Test: `tests/test_language_handler.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_language_handler.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import LangCb
from quantuum.db.models import Account

from .conftest import build_translator


def _fake_query():
    msg = SimpleNamespace(answer=AsyncMock())
    return SimpleNamespace(message=msg, answer=AsyncMock()), msg


async def test_set_language_persists_and_welcomes(session, default_tenant):
    from quantuum.bot.handlers import language

    i18n = await build_translator(session, default_tenant.id)  # ru
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="900"
    )
    query, msg = _fake_query()

    await language.on_set_language(
        query, LangCb(action="setup", lang="en"), acc, i18n
    )

    # Persisted to the DB
    row = (
        await session.execute(select(Account).where(Account.id == acc.id))
    ).scalar_one()
    await session.refresh(row)
    assert row.preferred_lang == "en"

    # setup → English welcome, then the menu
    assert msg.answer.await_args_list[0].args[0] == "Hello! I will build your astrological reading ✨"
    assert query.answer.await_count == 1


async def test_set_language_menu_change_confirms(session, default_tenant):
    from quantuum.bot.handlers import language

    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="901"
    )
    query, msg = _fake_query()

    await language.on_set_language(
        query, LangCb(action="set", lang="en"), acc, i18n
    )

    # "set" → confirmation text (English), not the welcome
    assert msg.answer.await_args_list[0].args[0] == "Language updated."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_language_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.handlers.language'`

- [ ] **Step 3a: Create the handler**

Create `src/quantuum/bot/handlers/language.py`:

```python
from aiogram import Router
from aiogram.types import CallbackQuery

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.bot.ui.callbacks import LangCb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.i18n import Translator

router = Router()


@router.callback_query(LangCb.filter())
async def on_set_language(
    query: CallbackQuery, callback_data: LangCb, account: Account, i18n: Translator
) -> None:
    lang = callback_data.lang
    # Persist on a fresh session — the middleware-injected `account` is detached.
    async with get_sessionmaker()() as session:
        acc = await session.get(Account, account.id)
        if acc is not None:
            acc.preferred_lang = lang
            await session.commit()
    # The injected i18n still carries the old language; build one for the new lang.
    new_i18n = Translator(tenant_id=account.tenant_id, lang=lang)
    if callback_data.action == "setup":
        await query.message.answer(await new_i18n("start.welcome"))
    else:
        await query.message.answer(await new_i18n("lang.changed"))
    await show_main_menu(query.message, new_i18n)
    await query.answer()
```

- [ ] **Step 3b: Register the router in app.py**

In `src/quantuum/bot/app.py`, add `language` to the handler import block and include its router after `start`:

```python
    from quantuum.bot.handlers import (
        buy,
        daily,
        generate,
        history,
        language,
        menu,
        onboarding,
        profile,
        qa,
        start,
        transits,
    )

    dp.include_router(start.router)
    dp.include_router(language.router)
    dp.include_router(buy.router)
```

(Leave the remaining `include_router` lines unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_language_handler.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/language.py src/quantuum/bot/app.py tests/test_language_handler.py
git commit -m "feat(i18n): language handler sets Account.preferred_lang"
```

---

### Task 4: First-entry language gate in start.py

**Files:**
- Modify: `src/quantuum/bot/handlers/start.py`
- Test: `tests/test_bot_start_menu_profile.py` (update `test_on_start_sends_welcome_and_menu`; add a picker test)

- [ ] **Step 1: Update + add the failing tests**

In `tests/test_bot_start_menu_profile.py`, **replace** `test_on_start_sends_welcome_and_menu` with the two tests below (the old one called `on_start(msg, i18n)`; the signature now takes `account` + `tenant_id`):

```python
async def test_on_start_with_lang_set_sends_welcome_and_menu(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="600"
    )
    acc.preferred_lang = "ru"  # already chosen → no picker
    msg = FakeMessage("/start")
    await start.on_start(msg, acc, default_tenant.id, i18n)

    welcome = msg.answers[0][0]
    assert welcome == "Привет! Я построю твой астрологический разбор ✨"
    menu_text, menu_markup = msg.answers[1]
    assert menu_text == "Главное меню:"
    assert set(_reply_texts(menu_markup)) == {
        "🔮 Разбор", "❓ Спросить астролога", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь", "🌐 Язык",
    }


async def test_on_start_first_time_shows_language_picker(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.callbacks import LangCb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="601"
    )  # preferred_lang is None → picker
    msg = FakeMessage("/start")
    await start.on_start(msg, acc, default_tenant.id, i18n)

    assert len(msg.answers) == 1  # picker only, no welcome/menu yet
    prompt, markup = msg.answers[0]
    assert prompt == "Выбери язык:"
    codes = {LangCb.unpack(b.callback_data).lang for row in markup.inline_keyboard for b in row}
    assert codes == {"ru", "en"}
```

Note: `test_on_help_btn_sends_help_text` already asserts a menu label set — it must also include `"🌐 Язык"` after Task 5. It is updated in Task 5, not here.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot_start_menu_profile.py::test_on_start_with_lang_set_sends_welcome_and_menu tests/test_bot_start_menu_profile.py::test_on_start_first_time_shows_language_picker -v`
Expected: FAIL (`on_start()` takes 2 positional args / picker not shown). The welcome test will also fail on the menu-label set until Task 5 adds the button — that is expected; it passes after Task 5. Proceed.

- [ ] **Step 3: Rewrite start.py**

Replace the contents of `src/quantuum/bot/handlers/start.py`:

```python
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.bot.ui.keyboards import language_picker_kb
from quantuum.db.models import Account
from quantuum.i18n import Translator

router = Router()


@router.message(CommandStart())
async def on_start(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    if account.preferred_lang is None:
        await message.answer(
            await i18n("lang.prompt"),
            reply_markup=await language_picker_kb(tenant_id, action="setup"),
        )
        return
    await message.answer(await i18n("start.welcome"))
    await show_main_menu(message, i18n)
```

- [ ] **Step 4: Run test to verify the picker test passes**

Run: `uv run pytest tests/test_bot_start_menu_profile.py::test_on_start_first_time_shows_language_picker -v`
Expected: PASS
(The welcome test still fails on the menu-label set until Task 5 — that is expected.)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/start.py tests/test_bot_start_menu_profile.py
git commit -m "feat(i18n): ask language on first /start"
```

---

### Task 5: 🌐 Language menu button

**Files:**
- Modify: `src/quantuum/bot/ui/text.py` (`MENU_BUTTON_KEYS`)
- Modify: `src/quantuum/bot/ui/keyboards.py` (`main_menu_kb`)
- Modify: `src/quantuum/bot/handlers/menu.py` (label set + routing handler)
- Test: `tests/test_bot_start_menu_profile.py` (update help-button label set; add menu-button test)

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/test_bot_start_menu_profile.py`, update the label-set assertion inside `test_on_help_btn_sends_help_text` to include the language button:

```python
    assert set(_reply_texts(markup)) == {
        "🔮 Разбор", "❓ Спросить астролога", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь", "🌐 Язык",
    }
```

Add a new test for the menu button routing:

```python
async def test_language_button_opens_picker(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.handlers import menu as menu_mod
    from quantuum.bot.ui.callbacks import LangCb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    msg = FakeMessage("🌐 Язык")
    await menu_mod.on_language_btn(msg, default_tenant.id, i18n)

    prompt, markup = msg.answers[0]
    assert prompt == "Выбери язык:"
    actions = {LangCb.unpack(b.callback_data).action for row in markup.inline_keyboard for b in row}
    assert actions == {"set"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot_start_menu_profile.py::test_language_button_opens_picker tests/test_bot_start_menu_profile.py::test_on_help_btn_sends_help_text -v`
Expected: FAIL (`menu` has no `on_language_btn`; help label set lacks `🌐 Язык`).

- [ ] **Step 3a: Add `btn.language` to MENU_BUTTON_KEYS**

In `src/quantuum/bot/ui/text.py`, extend the tuple:

```python
MENU_BUTTON_KEYS = (
    "btn.generate", "btn.ask", "btn.transits", "btn.daily",
    "btn.profile", "btn.history", "btn.help", "btn.language",
)
```

- [ ] **Step 3b: Render the button in main_menu_kb**

In `src/quantuum/bot/ui/keyboards.py`, update `main_menu_kb` to add the language button and re-balance the layout to 8 buttons:

```python
async def main_menu_kb(i18n: Translator) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=await i18n("btn.generate"))
    b.button(text=await i18n("btn.ask"))
    b.button(text=await i18n("btn.transits"))
    b.button(text=await i18n("btn.daily"))
    b.button(text=await i18n("btn.profile"))
    b.button(text=await i18n("btn.history"))
    b.button(text=await i18n("btn.help"))
    b.button(text=await i18n("btn.language"))
    b.adjust(2, 2, 2, 2)
    return b.as_markup(resize_keyboard=True, is_persistent=True)
```

- [ ] **Step 3c: Add the routing handler in menu.py**

In `src/quantuum/bot/handlers/menu.py`, add the label set near the other `_*_LABELS` constants:

```python
_LANGUAGE_LABELS = text.menu_button_labels("btn.language")
```

Add the import for the picker (extend the existing `from quantuum.bot.ui.keyboards import ...` line):

```python
from quantuum.bot.ui.keyboards import language_picker_kb, main_menu_kb
```

Add the handler (e.g. after `on_help_btn`):

```python
@router.message(F.text.in_(_LANGUAGE_LABELS))
async def on_language_btn(message: Message, tenant_id: int, i18n: Translator) -> None:
    await message.answer(
        await i18n("lang.prompt"),
        reply_markup=await language_picker_kb(tenant_id, action="set"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot_start_menu_profile.py -v`
Expected: PASS (including `test_on_start_with_lang_set_sends_welcome_and_menu` from Task 4, now that `🌐 Язык` is in the menu).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/ui/text.py src/quantuum/bot/ui/keyboards.py src/quantuum/bot/handlers/menu.py tests/test_bot_start_menu_profile.py
git commit -m "feat(i18n): 🌐 Language button in the main menu"
```

---

### Task 6: Localize onboarding.py

**Files:**
- Modify: `src/quantuum/bot/handlers/onboarding.py`
- Test: `tests/test_bot_onboarding.py` (add `FakeI18n`; pass it to handlers; add localization assertions)

- [ ] **Step 1: Add FakeI18n + update existing tests to fail**

At the top of `tests/test_bot_onboarding.py`, add a fake translator helper:

```python
from quantuum.i18n.resolver import safe_format
from quantuum.i18n.seed_strings import BASE_STRINGS


class FakeI18n:
    """Returns the seeded RU string for a key, formatted with vars (no DB)."""

    lang = "ru"

    async def __call__(self, key, default=None, **vars):
        template = BASE_STRINGS.get(key, {}).get("ru", default if default is not None else key)
        return safe_format(template, vars)
```

Then update the existing handler-call tests to pass `i18n=FakeI18n()`:

- In `test_birth_place_location_saves_with_derived_tz`:
  ```python
      await ob.on_birth_place_location(message, state, account=account, i18n=FakeI18n())
  ```
- In `test_birth_place_location_falls_back_when_reverse_fails`:
  ```python
      await ob.on_birth_place_location(message, state, account=account, i18n=FakeI18n())
  ```
- In `test_birth_place_text_geocodes_then_confirms`:
  ```python
      await ob.on_birth_place_text(message, state, i18n=FakeI18n())
  ```
  and change the final assertion (the confirm now reuses `profile.place.confirm`, which has **no** timezone line):
  ```python
      text = message.answer.await_args.args[0]
      assert "Bratsk" in text
      assert "Asia/Irkutsk" not in text  # tz line dropped (matches profile place-only flow)
  ```
- In `test_birth_place_text_not_found_reprompts`:
  ```python
      await ob.on_birth_place_text(message, state, i18n=FakeI18n())
  ```
- In `test_geo_confirm_saves`:
  ```python
      await ob.on_geo_confirm(query, OnboardCb(action="geo_confirm"), state, account=account, i18n=FakeI18n())
  ```
- In `test_geo_retry_returns_to_birth_place`:
  ```python
      await ob.on_geo_retry(query, OnboardCb(action="geo_retry"), state, i18n=FakeI18n())
  ```

Add two new localization tests:

```python
async def test_on_full_name_invalid_localised(default_tenant):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    state = _State({})
    state.state = ob.Onboarding.full_name
    message = SimpleNamespace(text="   ", answer=AsyncMock())

    await ob.on_full_name(message, state, i18n=FakeI18n())

    assert message.answer.await_args.args[0] == BASE_STRINGS["onb.error.full_name"]["ru"]


async def test_on_birth_date_prompt_localised_en(session, default_tenant):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    from .conftest import build_translator

    i18n = await build_translator(session, default_tenant.id, lang="en")
    state = _State({})
    state.state = ob.Onboarding.full_name
    message = SimpleNamespace(text="Anna", answer=AsyncMock())

    await ob.on_full_name(message, state, i18n=i18n)

    # advancing to birth_date prompts the EN string
    assert message.answer.await_args.args[0] == BASE_STRINGS["onb.prompt.birth_date"]["en"]
    assert state.state == ob.Onboarding.birth_date
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot_onboarding.py -v`
Expected: FAIL (handlers don't accept `i18n=`; new localization tests fail).

- [ ] **Step 3: Rewrite onboarding.py to use i18n**

In `src/quantuum/bot/handlers/onboarding.py`, add the import:

```python
from quantuum.i18n import Translator
```

Replace the handler bodies and the two helpers (`geo_confirm_kb`, `_DONE_MSG` removed; confirm/retry reuse `profile.place.*`). The non-rendering helpers (`parse_*`, `build_profile_data`, `save_collected_profile`, `_finalize_profile`) are unchanged. New handler/keyboard code:

```python
async def geo_confirm_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_confirm"),
            callback_data=OnboardCb(action="geo_confirm").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_retry"),
            callback_data=OnboardCb(action="geo_retry").pack(),
        )
    )
    return builder.as_markup()


@router.callback_query(OnboardCb.filter(F.action == "start"))
async def start_onboarding(query: CallbackQuery, state: FSMContext, i18n: Translator) -> None:
    await state.set_state(Onboarding.full_name)
    await query.message.answer(
        await i18n("onb.prompt.full_name"), reply_markup=await cancel_kb(i18n)
    )
    await query.answer()


@router.message(Onboarding.full_name)
async def on_full_name(message: Message, state: FSMContext, i18n: Translator) -> None:
    name = parse_required_text(message.text)
    if name is None:
        await message.answer(await i18n("onb.error.full_name"))
        return
    await state.update_data(full_name=name)
    await state.set_state(Onboarding.birth_date)
    await message.answer(await i18n("onb.prompt.birth_date"))


@router.message(Onboarding.birth_date)
async def on_birth_date(message: Message, state: FSMContext, i18n: Translator) -> None:
    parsed = parse_birth_date(message.text)
    if parsed is None:
        await message.answer(await i18n("onb.error.birth_date"))
        return
    await state.update_data(birth_date=parsed.isoformat())
    await state.set_state(Onboarding.birth_time)
    await message.answer(await i18n("onb.prompt.birth_time"))


@router.message(Onboarding.birth_time)
async def on_birth_time(message: Message, state: FSMContext, i18n: Translator) -> None:
    parsed = parse_birth_time(message.text)
    if parsed is None:
        await message.answer(await i18n("onb.error.birth_time"))
        return
    await state.update_data(birth_time=parsed.isoformat())
    await state.set_state(Onboarding.birth_place)
    await message.answer(await i18n("onb.prompt.birth_place"))


@router.message(Onboarding.birth_place, F.location)
async def on_birth_place_location(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    tz = coords_to_timezone(lat, lon)
    geo = await reverse(lat, lon)
    display = geo.display_name if geo is not None else f"📍 {lat:.4f}, {lon:.4f}"
    await state.update_data(
        birth_place=display, latitude=str(lat), longitude=str(lon), timezone=tz
    )
    await _finalize_profile(state, account)
    await message.answer(await i18n("onb.done"))


@router.message(Onboarding.birth_place, F.text)
async def on_birth_place_text(message: Message, state: FSMContext, i18n: Translator) -> None:
    results = await geocode((message.text or "").strip())
    if not results:
        await message.answer(await i18n("profile.place.not_found"))
        return
    top = results[0]
    tz = coords_to_timezone(top.lat, top.lon)
    await state.update_data(
        birth_place=top.display_name,
        latitude=str(top.lat),
        longitude=str(top.lon),
        timezone=tz,
    )
    await state.set_state(Onboarding.birth_place_confirm)
    await message.answer(
        await i18n("profile.place.confirm", place=top.display_name),
        reply_markup=await geo_confirm_kb(i18n),
    )


@router.message(Onboarding.birth_place)
async def on_birth_place_other(message: Message, state: FSMContext, i18n: Translator) -> None:
    await message.answer(await i18n("profile.prompt.birth_place"))


@router.callback_query(OnboardCb.filter(F.action == "geo_confirm"), Onboarding.birth_place_confirm)
async def on_geo_confirm(
    query: CallbackQuery, callback_data: OnboardCb, state: FSMContext,
    account: Account, i18n: Translator,
) -> None:
    await _finalize_profile(state, account)
    await query.message.answer(await i18n("onb.done"))
    await query.answer()


@router.callback_query(OnboardCb.filter(F.action == "geo_retry"), Onboarding.birth_place_confirm)
async def on_geo_retry(
    query: CallbackQuery, callback_data: OnboardCb, state: FSMContext, i18n: Translator
) -> None:
    await state.set_state(Onboarding.birth_place)
    await query.message.answer(await i18n("profile.prompt.birth_place"))
    await query.answer()
```

Also delete the now-unused `_DONE_MSG` constant. Keep `from aiogram.types import CallbackQuery, InlineKeyboardButton, Message` and `from aiogram.utils.keyboard import InlineKeyboardBuilder` (still used by `geo_confirm_kb`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot_onboarding.py -v`
Expected: PASS (all, including the two new localization tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/onboarding.py tests/test_bot_onboarding.py
git commit -m "feat(i18n): localize the onboarding flow (onb.* + reuse profile.place.*)"
```

---

### Task 7: Fix the four `or "ru"` fallbacks → tenant default

**Files:**
- Modify: `src/quantuum/tasks/daily.py:65`
- Modify: `src/quantuum/tasks/transits.py:53`
- Modify: `src/quantuum/api/routes/me.py:223` and `:302`
- Test: `tests/test_i18n_resolver.py` (guard test for the contract these sites rely on)

- [ ] **Step 1: Write the guard test**

This is the contract the fix depends on. (`resolve_lang` is already correct; this test pins it and documents the intended fallback so the call-site edits are safe.) Add to `tests/test_i18n_resolver.py`:

```python
async def test_resolve_lang_falls_back_to_tenant_default(session):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.db.models import Tenant
    from quantuum.i18n.resolver import resolve_lang

    # An English-default tenant.
    tenant = Tenant(slug="en-tenant", display_name="EN")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    await ensure_tenant_default_language(session, tenant.id, default_lang="en")
    await session.commit()

    # No preference and no Telegram hint → the tenant default (en), NOT hardcoded ru.
    lang = await resolve_lang(
        session, tenant_id=tenant.id, preferred_lang=None, tg_language_code=None
    )
    assert lang == "en"
```

- [ ] **Step 2: Run test to verify it passes (guard, already-correct contract)**

Run: `uv run pytest tests/test_i18n_resolver.py::test_resolve_lang_falls_back_to_tenant_default -v`
Expected: PASS. (Unlike a normal red-first test, this guards a contract that already holds; the real change in this task is the four mechanical call-site edits below, covered by the existing task/route suites in Step 4.)

- [ ] **Step 3a: Fix daily.py**

In `src/quantuum/tasks/daily.py`, add the import near the other `quantuum.i18n` import:

```python
from quantuum.i18n import resolve_lang
```

Replace line 65:

```python
        lang = account.preferred_lang or "ru"
```

with:

```python
        lang = await resolve_lang(
            session,
            tenant_id=account.tenant_id,
            preferred_lang=account.preferred_lang,
            tg_language_code=None,
        )
```

- [ ] **Step 3b: Fix transits.py**

In `src/quantuum/tasks/transits.py`, add the import:

```python
from quantuum.i18n import resolve_lang
```

Replace `lang=row.lang or "ru",` (line 53) with:

```python
                lang=await resolve_lang(
                    session,
                    tenant_id=row.tenant_id,
                    preferred_lang=row.lang,
                    tg_language_code=None,
                ),
```

- [ ] **Step 3c: Fix me.py (both sites)**

In `src/quantuum/api/routes/me.py`, add the import near the top with the other imports:

```python
from quantuum.i18n import resolve_lang
```

Replace both occurrences of:

```python
    lang = account.preferred_lang or "ru"
```

with:

```python
    lang = await resolve_lang(
        session,
        tenant_id=account.tenant_id,
        preferred_lang=account.preferred_lang,
        tg_language_code=None,
    )
```

(There are two — one in the Q&A route ~line 223, one in the transit route ~line 302. Both get the same replacement.)

- [ ] **Step 4: Run the affected suites to verify no regression**

Run: `uv run pytest tests/test_i18n_resolver.py tests/test_api_qa.py tests/test_transits_bot.py -v`
Expected: PASS. (If a `tests/test_daily*.py` exists, include it too.)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/tasks/daily.py src/quantuum/tasks/transits.py src/quantuum/api/routes/me.py tests/test_i18n_resolver.py
git commit -m "fix(i18n): fall back to tenant default lang, not hardcoded ru"
```

---

### Task 8: Full suite + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (all tests). Investigate and fix any failure before proceeding.

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: clean. Fix any issues (e.g. unused imports left in `onboarding.py` / `start.py`).

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint after i18n language-selection"
```

(Skip if there is nothing to commit.)

---

## Self-Review

**1. Spec coverage:**
- Picker (reusable, native labels, enabled langs, default-first) → Task 2. ✓
- `LangCb` setup/set → Tasks 2–3. ✓
- Language handler persists `preferred_lang`, setup→welcome / set→changed → Task 3. ✓
- First-entry gate (`preferred_lang is None`) → Task 4. ✓
- 🌐 menu button (text.py / keyboards.py / menu.py) → Task 5. ✓
- Localize onboarding.py via `onb.*` + reuse `profile.place.*` (drops tz line) → Task 6. ✓
- Four `or "ru"` fallbacks → Task 7. ✓
- New keys auto-seed (no live UPDATE) → covered by Task 1 (insert-only). ✓
- Tests for start gate, picker kb, set language, menu button, onboarding localization, fallback → Tasks 2–7. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. The one "if exists, include it too" note (Task 7 daily test) is conditional on an optional file, not a placeholder for required work.

**3. Type consistency:**
- `LangCb(action: str, lang: str)` consistent across callbacks.py, keyboards.py, handler, tests. ✓
- `language_picker_kb(tenant_id: int, *, action: str)` signature consistent across keyboards.py, start.py, menu.py, tests. ✓
- `Translator(tenant_id=…, lang=…)` matches the keyword-only constructor in `resolver.py`. ✓
- `on_start(message, account, tenant_id, i18n)` — the updated test calls it positionally with exactly these. ✓
- `resolve_lang(session, *, tenant_id, preferred_lang, tg_language_code)` matches resolver.py signature at all four call sites. ✓
- Onboarding handlers all gain `i18n: Translator`; the existing tests are updated to pass it. ✓
