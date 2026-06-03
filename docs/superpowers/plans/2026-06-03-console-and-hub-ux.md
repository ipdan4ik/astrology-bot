# Owner-Console & Hub-Bot UX Refactor (Workstream F) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the owner console navigable (working Transfer button, Referrals/Gifts toggles, consistent in-place Back navigation across submenus) and the hub onboarding recoverable (cancel keyboard on every prompt, a blanket `/cancel`, `ReplyKeyboardRemove` on exit paths), and move the last hardcoded Russian provisioning strings into i18n.

**Architecture:** `owner_console.py` builds the manage menu inline in `on_manage` and opens each submenu (Features, Branding, Referrals, Gifts) from its own callback. We (1) wire the existing-but-dead `OwnerManageCb(action="transfer")` button to the transfer FSM, (2) add `referrals`/`gifts` toggles to the features keyboard (the flags already exist in `FEATURE_KEYS`), (3) extract a shared manage-menu renderer + a `menu` back-callback and give every submenu a `‹ Back` row that re-renders the menu in place via `edit_text`. The hub onboarding (`master_onboarding.py`) gets a cancel keyboard on each text prompt, one `/cancel` handler covering all onboarding states, and `ReplyKeyboardRemove` on cancel + manual-token completion. `tasks/provision.py`'s hardcoded RU strings move to i18n (a Translator is built in the task from the tenant).

**Tech Stack:** aiogram (InlineKeyboardBuilder, FSM), i18n seed strings + 8 translation files, pytest. Bot tests assert on inline-keyboard `callback_data`/text and on `message.answer`/`edit_text` mock calls.

**Test command:** `uv run pytest <path> -v`. asyncio auto mode (no decorator). For each task READ the named existing test file first and mirror its callback/query/i18n mock construction and its keyboard-extraction helper (e.g. `_inline(markup)` flattening rows; `OwnerManageCb.unpack(b.callback_data)`). Do NOT weaken assertions.

**i18n key convention:** new keys get ru+en in `src/quantuum/i18n/seed_strings.py` AND an entry in each of the 8 files `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`. A helper test should assert the key exists in all 10 langs (mirror `tests/test_i18n_queue_failed_key.py`).

---

### Task 1: New i18n keys (Back, feature toggle labels, provision strings)

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` + all 8 `translations/*.py`
- Test: `tests/test_i18n_console_ux_keys.py` (create)

Add these keys (ru/en in seed_strings, plus all 8 translation files). Use natural translations; ru/en below, translate the rest faithfully:

- `owner.manage.kb.back` — ru: `"⬅️ Назад в меню"`, en: `"⬅️ Back to menu"`
- `owner.features.label.referrals` — ru: `"Рефералы"`, en: `"Referrals"`
- `owner.features.label.gifts` — ru: `"Подарки"`, en: `"Gifts"`
- `master.provision.manual_prompt` — ru: (copy the current `_MANUAL_TOKEN_PROMPT` text from `tasks/provision.py`), en: `"Automatic bot creation is unavailable. Create a new bot via @BotFather and send its token here in one message."`
- `master.provision.managed_prompt` — ru: (copy current `_MANAGED_PROMPT`), en: `"Tap the button below — Telegram will create the bot and I'll pick it up automatically. You can adjust the username on the creation screen."`
- `master.provision.managed_button` — ru: `"🤖 Создать бота"`, en: `"🤖 Create bot"`

- [ ] **Step 1: Write the failing test** (mirror `tests/test_i18n_queue_failed_key.py`)

```python
# tests/test_i18n_console_ux_keys.py
from quantuum.i18n.seed_strings import BASE_STRINGS

ALL_LANGS = {"ru", "en", "de", "es", "fr", "hi", "it", "pt", "tr", "zh"}
KEYS = [
    "owner.manage.kb.back",
    "owner.features.label.referrals",
    "owner.features.label.gifts",
    "master.provision.manual_prompt",
    "master.provision.managed_prompt",
    "master.provision.managed_button",
]


def test_console_ux_keys_present_in_all_langs():
    for key in KEYS:
        assert key in BASE_STRINGS, key
        for lang in ALL_LANGS:
            assert BASE_STRINGS[key].get(lang, "").strip(), f"{key}/{lang}"
```

- [ ] **Step 2: Run → fail.** `uv run pytest tests/test_i18n_console_ux_keys.py -v`
- [ ] **Step 3: Add the keys** to `seed_strings.py` (ru/en) and all 8 translation files.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/ tests/test_i18n_console_ux_keys.py
git commit -m "feat(i18n): console-UX nav + provision keys in all 10 languages"
```

---

### Task 2: Wire the dead Transfer button

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_console.py` (add `on_manage_transfer` callback handler near the transfer FSM, ~line 276)
- Test: `tests/test_owner_console_actions.py`

**Context:** the manage menu emits `OwnerManageCb(action="transfer", tenant_id=...)` (line 158) but no callback handler exists — only `/transfer <slug>`. Add a handler that owner-authorizes, sets the transfer FSM state, and prompts. Mirror `on_transfer_cmd` (line 277) but take `tenant_id` from the callback.

- [ ] **Step 1: Write the failing test**

Mirror `tests/test_owner_console_actions.py`'s transfer/owner setup. Assert: an OWNER tapping the transfer callback enters `OwnerTransfer.awaiting_target` (state set, tenant_id stored, prompt sent); an ADMIN is denied (`owner.no_rights`, no state set).

```python
async def test_transfer_button_enters_fsm_for_owner(session, default_tenant, ...):
    # owner actor; OwnerManageCb(action="transfer", tenant_id=default_tenant.id)
    state = <FSMContext mock as used in this file>
    await on_manage_transfer(query, callback_data, state, i18n)
    assert (await state.get_state()) == OwnerTransfer.awaiting_target.state
    data = await state.get_data()
    assert data["tenant_id"] == default_tenant.id
    # prompt shown
    query.message.answer.assert_awaited()

async def test_transfer_button_denied_for_admin(session, default_tenant, ...):
    # admin actor
    await on_manage_transfer(query, callback_data, state, i18n)
    assert (await state.get_state()) is None  # no FSM entered
```

NOTE: read how this file builds the `FSMContext`/`state` mock and the owner-vs-admin actor; mirror it exactly.

- [ ] **Step 2: Run → fail** (no `on_manage_transfer`). `uv run pytest tests/test_owner_console_actions.py -k transfer_button -v`

- [ ] **Step 3: Implement**

In `owner_console.py`, after the `OwnerTransfer` class / near `on_transfer_cmd`, add:

```python
@router.callback_query(OwnerManageCb.filter(F.action == "transfer"))
async def on_manage_transfer(
    query: CallbackQuery, callback_data: OwnerManageCb, state: FSMContext, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id,
            roles=("owner",),
        )
    if actor is None:
        await query.answer(await i18n("owner.no_rights"), show_alert=True)
        return
    await state.set_state(OwnerTransfer.awaiting_target)
    await state.update_data(tenant_id=callback_data.tenant_id)
    await query.message.answer(await i18n("owner.transfer.prompt"))
    await query.answer()
```

(Transfer is owner-only per the permissions workstream; the FSM target handler re-authorizes owner-only at apply time.)

- [ ] **Step 4: Run → pass.** `uv run pytest tests/test_owner_console_actions.py -v`
- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/owner_console.py tests/test_owner_console_actions.py
git commit -m "fix(owner): wire Transfer button to the transfer FSM"
```

---

### Task 3: Referrals + Gifts toggles in the features keyboard

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_console.py` — `_features_keyboard` (~line 435)
- Test: `tests/test_tenant_features_owner_console.py` (and/or `tests/test_tenant_features_menu.py`)

**Context:** `FEATURE_KEYS` already includes `"referrals"` and `"gifts"`, but `_features_keyboard` renders only the 4 core + 10 reading toggles (14). Add `referrals` and `gifts` as toggles too (→ 16), grouped as their own block after the readings block.

- [ ] **Step 1: Write the failing test**

Mirror the existing features-keyboard test (it counts `ofeat:toggle` callbacks — currently 14). Add/adjust a test asserting 16 toggles now, including `referrals` and `gifts` keys:

```python
async def test_features_keyboard_includes_referrals_and_gifts(...):
    # render the features keyboard for a tenant (reuse the file's render path)
    keys = [OwnerFeatureCb.unpack(cd).key for cd in toggle_callbacks]
    assert "referrals" in keys and "gifts" in keys
    assert len([c for c in toggle_callbacks if c.startswith("ofeat:toggle")]) == 16
```

NOTE: if the existing test hardcodes `== 14`, update it to `== 16` (intended — two toggles added).

- [ ] **Step 2: Run → fail.** `uv run pytest tests/test_tenant_features_owner_console.py -v`

- [ ] **Step 3: Implement**

In `_features_keyboard`, after the readings loop and before `b.adjust(...)`, add a referrals/gifts block:

```python
    for key, label_key in (
        ("referrals", "owner.features.label.referrals"),
        ("gifts", "owner.features.label.gifts"),
    ):
        text_label = f"{_mark(flags[key])} {await i18n(label_key)}"
        b.button(
            text=text_label,
            callback_data=OwnerFeatureCb(action="toggle", tenant_id=tenant_id, key=key).pack(),
        )

    b.adjust(2, 2, 2, 2, 2, 2, 2, 2)  # 16 toggles, 8 rows of 2
```

NOTE: the `flags` dict passed to `_features_keyboard` must include `referrals`/`gifts`. Check the caller (the features-open handler) — it likely builds `flags` from `FEATURE_KEYS` via `list_feature_states`/`is_feature_enabled`, which already covers all 16. If it builds a hardcoded subset, extend it to all `FEATURE_KEYS`. Verify `on_features_toggle` accepts the `referrals`/`gifts` keys (it toggles by key, so it should already).

- [ ] **Step 4: Run → pass.** `uv run pytest tests/test_tenant_features_owner_console.py tests/test_tenant_features_menu.py -v`
- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/owner_console.py tests/
git commit -m "feat(owner): add Referrals and Gifts toggles to features keyboard"
```

---

### Task 4: Shared manage-menu renderer + in-place Back navigation

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_console.py` — extract a manage-menu renderer; add a `menu` back-callback handler; add a `‹ Back` row to each submenu keyboard (Features, Branding, Referrals, Gifts); make submenu opens + Back use `edit_text`.
- Modify: `src/quantuum/bot/ui/callbacks.py` — add `"menu"` to `OwnerManageCb` action values (no new field needed; `tenant_id` already present).
- Test: `tests/test_owner_console_handlers.py`, `tests/test_tenant_branding_owner_console.py`, `tests/test_owner_referrals.py`, `tests/test_owner_gifts.py`

- [ ] **Step 1: Extract the renderer (refactor, no behavior change yet)**

Pull the manage-menu keyboard/text out of `on_manage` into a module-level helper:

```python
async def _manage_menu(tenant, i18n: Translator) -> tuple[str, "InlineKeyboardMarkup"]:
    builder = InlineKeyboardBuilder()
    # ... move the exact rows currently built inline in on_manage (stats, users,
    # features, branding, referrals, gifts, pause/resume, transfer, delete) ...
    text = await i18n(
        "owner.manage.title",
        display_name=tenant.display_name, slug=tenant.slug, status=tenant.status,
    )
    return text, builder.as_markup()
```

Update `on_manage` to call it: `text, markup = await _manage_menu(tenant, i18n); await message.answer(text, reply_markup=markup)`. Run the existing `tests/test_owner_console_handlers.py` to confirm the refactor is behavior-preserving (all still pass).

- [ ] **Step 2: Write the failing test for Back**

In `tests/test_tenant_branding_owner_console.py` (or features), add a test that the submenu keyboard contains a Back button emitting `OwnerManageCb(action="menu", tenant_id=...)`, and that tapping it re-renders the manage menu via `edit_text`:

```python
async def test_branding_submenu_has_back_to_menu(...):
    # open branding submenu (reuse file's path); extract its keyboard
    cbs = [b.callback_data for b in _inline(markup)]
    assert any(cd == OwnerManageCb(action="menu", tenant_id=T.id).pack() for cd in cbs)

async def test_manage_menu_back_callback_rerenders(...):
    # call the new on_manage_menu handler with OwnerManageCb(action="menu", tenant_id=T.id)
    await on_manage_menu(query, callback_data, i18n)
    query.message.edit_text.assert_awaited()  # in-place
```

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement the back-callback + Back rows**

Add the handler:

```python
@router.callback_query(OwnerManageCb.filter(F.action == "menu"))
async def on_manage_menu(
    query: CallbackQuery, callback_data: OwnerManageCb, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
    if tenant is None:
        await query.answer(await i18n("owner.manage.not_found"), show_alert=True)
        return
    text, markup = await _manage_menu(tenant, i18n)
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()
```

Then add a `‹ Back` row to each submenu keyboard builder (`_features_keyboard`, `_branding_keyboard`, `_referrals_keyboard`, `_gifts_keyboard`): append

```python
    b.row(InlineKeyboardButton(
        text=await i18n("owner.manage.kb.back"),
        callback_data=OwnerManageCb(action="menu", tenant_id=tenant_id).pack(),
    ))
```

(For `_features_keyboard`, add the Back row AFTER `b.adjust(...)` using `b.row(...)` so it sits on its own row.) Each keyboard builder must accept/已有 `tenant_id` and `i18n` — they do.

For **in-place** opening: in each submenu's `*_open` callback handler, change `query.message.answer(text, reply_markup=...)` to `query.message.edit_text(text, reply_markup=...)` so the submenu replaces the menu message and Back replaces it back. (Stats and Users are larger/list flows — for Stats, also give its result an edit_text + Back row if it currently uses `answer`; Users list already has its own back-to-list nav, leave its internal paging as-is but ensure the user-card view can return to the manage menu if that's cheap — otherwise leave Users as-is and note it.)

NOTE for implementer: READ each `*_open` handler and keyboard builder; apply the Back row + `edit_text` consistently. Some existing tests assert `query.message.answer` was called for a submenu open — update those to assert `edit_text` (intended in-place behavior; not a weakening). Keep authorization checks intact.

- [ ] **Step 5: Run → pass.** Run all four submenu test files + `tests/test_owner_console_handlers.py`.
- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/owner_console.py src/quantuum/bot/ui/callbacks.py tests/
git commit -m "feat(owner): in-place Back navigation across console submenus"
```

---

### Task 5: Hub onboarding — cancel keyboard on every prompt

**Files:**
- Modify: `src/quantuum/bot/handlers/master_onboarding.py` — attach `master_cancel_kb(i18n)` to the `on_slug` and `on_display_name` prompts (currently free-text with no keyboard); the slug-entry and confirm prompts already have keyboards.
- Test: `tests/test_master_onboarding.py`

- [ ] **Step 1: Write the failing test**

Mirror the onboarding test setup. Assert that after `on_slug` advances to `display_name`, the prompt message carries a cancel keyboard (reply_markup present with the cancel callback), and likewise after `on_display_name` advances to `default_lang`.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement**

In `on_slug` and `on_display_name`, pass `reply_markup=await master_cancel_kb(i18n)` on the prompt `answer(...)` calls (the next-step prompts). Keep the validation-error `answer(...)` calls as-is or also attach the cancel kb (prefer attaching for consistency).

- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_onboarding.py tests/test_master_onboarding.py
git commit -m "feat(hub): cancel keyboard on every onboarding prompt"
```

---

### Task 6: Hub onboarding — blanket /cancel + ReplyKeyboardRemove

**Files:**
- Modify: `src/quantuum/bot/handlers/master_onboarding.py` — add a `/cancel` command handler that covers ALL onboarding states (`OwnerOnboarding.*` and `ManualToken.awaiting`); send `ReplyKeyboardRemove` on the cancel path and on the manual-token completion path.
- Test: `tests/test_master_onboarding.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_cancel_command_clears_any_onboarding_state(...):
    # set state to ManualToken.awaiting, send /cancel
    await on_onboarding_cancel_cmd(message, state, i18n)
    assert (await state.get_state()) is None
    # confirmation message sent with ReplyKeyboardRemove
    _, kwargs = message.answer.call_args
    from aiogram.types import ReplyKeyboardRemove
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardRemove)

async def test_manual_token_success_removes_keyboard(...):
    # patch validate_bot_token + finalize_provisioning; run on_manual_token
    # assert the done message includes ReplyKeyboardRemove
```

NOTE: the existing `OwnerOnboardCb(action="cancel")` callback handler (`on_cancel`) already clears state; this adds a `/cancel` COMMAND path and ensures `ReplyKeyboardRemove`.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement**

Add a command handler bound to `/cancel` for the onboarding states. aiogram allows binding multiple states via `StateFilter`:

```python
from aiogram.filters import StateFilter
from aiogram.types import ReplyKeyboardRemove

@router.message(
    Command("cancel"),
    StateFilter(
        OwnerOnboarding.slug, OwnerOnboarding.display_name,
        OwnerOnboarding.default_lang, OwnerOnboarding.confirm,
        ManualToken.awaiting,
    ),
)
async def on_onboarding_cancel_cmd(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(
        await i18n("master.onboard.cancelled"), reply_markup=ReplyKeyboardRemove()
    )
```

In `on_cancel` (the callback) and `on_manual_token` (success), add `reply_markup=ReplyKeyboardRemove()` to the final `answer(...)` (mirroring `on_managed_bot_created` which already does this).

- [ ] **Step 4: Run → pass.** Run the whole `tests/test_master_onboarding.py`.
- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_onboarding.py tests/test_master_onboarding.py
git commit -m "feat(hub): blanket /cancel and ReplyKeyboardRemove on onboarding exit"
```

---

### Task 7: Localize provisioning prompts (provision.py i18n)

**Files:**
- Modify: `src/quantuum/tasks/provision.py` — replace `_MANUAL_TOKEN_PROMPT`, `_MANAGED_PROMPT`, `_MANAGED_BUTTON` with i18n lookups via a Translator built from the tenant being provisioned.
- Test: `tests/test_task_provision.py`

- [ ] **Step 1: Inspect**

Read `tasks/provision.py` to see how `provision_tenant` obtains a session and the `tenant_id`, and how `master_bot.send_message` is called. The Translator is built via `Translator.build(session, tenant_id=..., preferred_lang=..., tg_language_code=None)` (see `tests/conftest.py::build_translator` and `bootstrap.ensure_base_strings`/`ensure_tenant_default_language`). Use the tenant's default lang.

- [ ] **Step 2: Write the failing test**

Mirror `tests/test_task_provision.py`. Assert the prompts are resolved via i18n (e.g. the sent text equals the seeded `master.provision.*` value for the tenant's lang) rather than the hardcoded Russian constant. A simple contract: patch/inspect `master_bot.send_message` and assert the text matches `await i18n("master.provision.manual_prompt")` for the provisioned tenant's language.

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement**

In `provision_tenant` (and `_managed_bot_keyboard`), build a Translator for the tenant and replace the constants:

```python
from quantuum.i18n import Translator
# inside the task, with a session + tenant_id available:
i18n = await Translator.build(session, tenant_id=tenant_id, preferred_lang=None, tg_language_code=None)
manual_prompt = await i18n("master.provision.manual_prompt")
managed_prompt = await i18n("master.provision.managed_prompt")
managed_button = await i18n("master.provision.managed_button")
```

Pass `managed_button` into the keyboard builder (make `_managed_bot_keyboard` take the label as an arg). Remove the three module-level constants (or keep as English fallbacks only if a Translator can't be built — prefer removing and always using i18n).

NOTE: ensure `ensure_base_strings` has been run for the DB the task uses (the runner seeds at startup; tests seed via `build_translator`/`ensure_base_strings`). If the task's session might lack strings, call `ensure_base_strings(session)` defensively before building the Translator, or rely on the startup seed.

- [ ] **Step 5: Run → pass.** `uv run pytest tests/test_task_provision.py -v`
- [ ] **Step 6: Commit**

```bash
git add src/quantuum/tasks/provision.py tests/test_task_provision.py
git commit -m "fix(provision): localize onboarding prompts via i18n"
```

---

### Task 8: Stage regression — full suite

- [ ] **Step 1: Run the whole suite.** `uv run pytest -q`
Expected: all green (prior baseline 2070 passed + this plan's new tests). Confirm `uv run alembic heads` is still the single head `d4f5a6b7c809` (this workstream adds no migrations).

- [ ] **Step 2: If anything fails**

Most likely: existing submenu tests asserting `message.answer` for a submenu open that now uses `edit_text`, or the features-toggle count test asserting `== 14`. These are INTENDED changes — update those tests to the new behavior (edit_text, 16 toggles). Do NOT weaken authorization/security assertions. If a feature toggle for `referrals`/`gifts` interacts with the existing referrals/gifts CONFIG submenus, ensure both still work (toggle = on/off; submenu = configure reward/expiry).

- [ ] **Step 3: Commit** any test updates with a clear message.

---

## Notes / scope

- Stats and the Users list/card flows: give Stats an in-place render + Back if cheap; the Users flow already has internal back-to-list nav — adding a manage-menu Back to the user-card view is nice-to-have, not required. Note in the final report whatever you did/skipped there.
- Referrals/Gifts now have BOTH a feature toggle (on/off, in the features keyboard) and a config submenu (reward amount / expiry days, from the manage menu) — these are complementary, not duplicates.
- After this plan, update the `audit-fix-sweep-progress` memory: F DONE → the entire audit fix sweep is complete; then the branch is ready for `superpowers:finishing-a-development-branch`.
