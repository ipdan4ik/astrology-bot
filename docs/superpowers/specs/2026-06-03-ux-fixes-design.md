# UX Fixes — Design Spec
**Date:** 2026-06-03  
**Scope:** 15 UX/UI issues found during full bot flow audit  
**Delivery:** 5 independent PRs, TDD throughout

---

## Background

A full audit of the bot's handlers, keyboards, and i18n strings identified 15 issues ranging from critical FSM bugs (users trapped with no exit) to minor text inconsistencies. Issues are grouped into 5 thematically cohesive PRs.

---

## PR1 — FSM Cancel (QA, Divination, Onboarding)

**Issues:** #1, #2, #6  
**Files:** `qa.py`, `divination.py`, `onboarding.py`

### Problem
Three FSM flows trap the user with no cancel path:
1. `Ask.awaiting_question` — `start_ask()` shows no cancel button; any menu button press is treated as a question
2. `Divination.awaiting_question` — only a "Skip" button; user can skip the question but cannot abort the reading
3. Onboarding multi-step — `cancel_kb` is sent only at step 1 (full_name); subsequent steps and error messages send no keyboard, burying the cancel button in chat history

### Design

**QA (`qa.py:36–39`):**  
Add `reply_markup=await cancel_kb(i18n)` to the `start_ask()` answer. The existing `on_cancel` handler in `menu.py` has no state filter and already handles `OnboardCb(action="cancel")` in any FSM state — no new handler needed.

**Divination (`divination.py:77–90`):**  
Replace the inline keyboard with a combined keyboard built by a new helper `_divination_question_kb(i18n)` containing two buttons:
- "Пропустить" → `DivinationCb(action="skip")`
- "✖️ Отмена" → `OnboardCb(action="cancel")` (reuses existing handler)

**Onboarding (`onboarding.py`):**  
Add `reply_markup=await cancel_kb(i18n)` to every `.answer()` call in the FSM flow — both the step prompts on success (birth_date, birth_time, birth_place) and all error responses. This ensures the cancel button is always visible in the most recent message regardless of which step the user is on.

### Tests (TDD)
New file `tests/test_fsm_cancel.py`:
- In `Ask.awaiting_question`: cancel callback → state cleared, main menu shown
- In `Divination.awaiting_question`: cancel callback → state cleared, main menu shown
- In `Onboarding.birth_date`: cancel callback → state cleared, main menu shown
- Each prompt in onboarding flow contains an inline keyboard with `OnboardCb(action="cancel")`

---

## PR2 — No-profile Action Buttons

**Issues:** #4, #5  
**Files:** `readings.py`, `divination.py`, `qa.py`, `transits.py`, `daily.py`

### Problem
Five handlers show a plain-text error when the user has no natal profile, with no actionable button. The blueprint handler (`generate.py`) already shows `profile_kb(has_profile=False)` — this pattern needs to be applied consistently.

### Design

Add `reply_markup=await profile_kb(has_profile=False, i18n=i18n)` to the no-profile response in each of the five handlers:

| Handler | Location |
|---------|----------|
| `readings.py` | `on_reading_choice()` — `query.message.answer(no_profile)` |
| `divination.py` | `on_divination_choice()` — `query.message.answer(no_profile)` |
| `qa.py` | `_submit()` — `message.answer(no_profile)` |
| `transits.py` | `run_transits()` — `message.answer(no_profile)` |
| `daily.py` | `run_daily_settings()` — `message.answer(no_profile)` |

The "📝 Заполнить профиль" button uses `OnboardCb(action="start")` which the existing `onboarding.py` handler catches — no new routing needed.

**String cleanup:** `qa.no_profile` and `transit.no_profile` currently end with `(/profile)`. With a button present this is redundant — remove the `/profile` suffix from both strings in `seed_strings.py`.

### Tests (TDD)
New file `tests/test_no_profile_cta.py`:  
For each of the 5 handlers: calling without a profile → response contains an inline keyboard with a button whose callback data unpacks to `OnboardCb(action="start")`.

---

## PR3 — History Navigation Refactor

**Issues:** #7, #8  
**Files:** `history.py`, `callbacks.py`

### Problem
1. Every pagination and "Back" action calls `target.answer()` — creates a new message each time, cluttering the chat
2. "Back" from a blueprint detail always returns to page 0, losing the user's position

### Design

**Edit-in-place for pagination (#7):**

Refactor `_render_list()` into a pure function `_build_list_view(account, i18n, page) → (str, InlineKeyboardMarkup | None)` that returns content without sending. Three call sites behave differently:

- `show_history()` (reply keyboard button, initial load): calls `message.answer(text, reply_markup=kb)` then `_render_readings()` — unchanged behavior
- `on_page()` (inline pagination): calls `query.message.edit_text(text, reply_markup=kb)` — edits in place ✓
- `on_back()` (return from detail): calls `query.message.answer(text, reply_markup=kb)` — still sends a new message (the detail and list are separate messages; edit is not applicable here)

`_render_readings()` is called **only** from `show_history()` — pagination no longer re-sends the readings section.

**Page memory in Back button (#8):**

1. Add `page: int = 0` to `BlueprintCb` in `callbacks.py`
2. `on_open()` already receives `HistoryCb` with `callback_data.page` — pass it through to `blueprint_detail_kb(bp_id, can_download, i18n, page=callback_data.page)`
3. `blueprint_detail_kb()` gains a `page` parameter; Back button is built as `BlueprintCb(action="back", bp_id=bp_id, page=page)`
4. `on_back()` uses `callback_data.page` when calling `_build_list_view()`

### Tests (TDD)
New/extended `tests/test_history.py`:
- `on_page` callback → `edit_text` called, `answer` not called
- `on_back` with `page=2` → `_build_list_view` called with `page=2`
- `blueprint_detail_kb(bp_id, can_download, i18n, page=3)` → Back button unpacks to `BlueprintCb(action="back", page=3)`
- `show_history()` → `answer` called (not edit), `_render_readings` called

---

## PR4 — String / Text Fixes

**Issues:** #3, #10, #11, #12, #13  
**Files:** `seed_strings.py`, `gift.py`, `divination.py`

### Changes

**#3 — Gift cancel shows wrong message (`gift.py:150`):**  
After `/cancel` in `Gift.awaiting_amount`, bot currently replies with `gift.cancel_hint` ("Отправьте /cancel чтобы отменить."). Fix: replace with a new key `gift.cancelled` → `"Отменено."` / `"Cancelled."` Add key to `seed_strings.py`, update the one call site in `gift.py`.

**#10 — `help.text` outdated:**  
Rewrite both `ru` and `en` values to list all active features: Blueprint, QA, Readings (submenu), Transits, Daily horoscope, Profile, History, Language, Invite, Gift. Remove the stale `/start /profile /blueprint` commands line; keep the support handle.

**#11 — `btn.gift` missing emoji:**  
`"Подарок"` → `"🎁 Подарок"` / `"🎁 Gift"` in `seed_strings.py`. Also update the 8 language translation files (`es.py`, `de.py`, `fr.py`, `it.py`, `pt.py`, `tr.py`, `zh.py`, `hi.py`) — each already has `btn.gift` without an emoji prefix; add the appropriate emoji to each.

**#12 — `onb.done` promotes `/blueprint` command:**  
`"Команда /blueprint сгенерирует твой разбор."` → `"Нажми «🔮 Разбор» в меню ниже."` / `"Tap «🔮 Reading» in the menu below."` — guides users to the persistent reply keyboard.

**#13 — Divination: duplicate skip hint:**  
`divination.py:85–90` currently concatenates `divination.question_prompt` + `"\n"` + `divination.question_hint`. The hint ("Или нажмите кнопку «Пропустить» ниже") duplicates what the button already communicates. Remove the concatenation in `divination.py`; delete the `divination.question_hint` key from `seed_strings.py` and from all 8 language translation files (`es.py`, `de.py`, `fr.py`, `it.py`, `pt.py`, `tr.py`, `zh.py`, `hi.py`) where it exists.

### Tests (TDD)
New/extended `tests/test_strings.py`:
- Gift cancel handler responds with `gift.cancelled` text, not `gift.cancel_hint`
- Divination question message does not contain the `question_hint` text
- `btn.gift` value starts with `🎁`

---

## PR5 — New UX Elements

**Issues:** #9, #14, #15  
**Files:** `keyboards.py`, `menu.py`, `daily.py`, `divination.py`, `qa.py`, `seed_strings.py`

### Design

**#9 — Buy button in main menu:**  
Add `btn.buy` → `"💳 Купить"` / `"💳 Buy"` to `seed_strings.py`. Add placeholder translations in all 8 language translation files. In `keyboards.py:main_menu_kb()`, add the button unconditionally (no feature gate — purchase is always available). In `menu.py`, add `_BUY_LABELS = text.menu_button_labels("btn.buy")` and a handler `on_buy_btn` that calls `show_buy_menu()` from `buy.py`.

**#14 — CTA after moderation block:**  
In `divination.py` (`on_divination_question`, line 253–263) and `qa.py` (`_submit`, line 110–111): after `await message.answer(response_text)` add `reply_markup=await main_menu_kb(i18n, account.tenant_id)`. Both handlers already have `account` in scope. The explicit re-send of the persistent keyboard visually signals the user is back at the main menu.

**#15 — Daily horoscope: Close button:**  
Add `daily.kb.close` → `"✅ Готово"` / `"✅ Done"` to `seed_strings.py`. Add placeholder translations in all 8 language translation files. In `daily.py:_daily_view()`, add `DailyCb(action="close")` button as the last row of the keyboard. New handler:

```python
@router.callback_query(DailyCb.filter(F.action == "close"))
async def on_daily_close(query: CallbackQuery, i18n: Translator) -> None:
    await query.message.delete()
    await query.answer()
```

Deleting the message is cleaner than editing to remove buttons.

### Tests (TDD)
New `tests/test_pr5_ux.py`:
- `main_menu_kb()` result contains `btn.buy` label
- `on_buy_btn` handler calls `show_buy_menu()`
- Moderation block in divination → response reply_markup is a `ReplyKeyboardMarkup`
- Moderation block in QA → same
- `on_daily_close` → `message.delete()` called

---

## Summary

| PR | Branch name | Files changed | New i18n keys | New test file |
|----|-------------|---------------|---------------|---------------|
| 1 | `fix/fsm-cancel` | `qa.py`, `divination.py`, `onboarding.py` | — | `test_fsm_cancel.py` |
| 2 | `fix/no-profile-cta` | `readings.py`, `divination.py`, `qa.py`, `transits.py`, `daily.py` | — | `test_no_profile_cta.py` |
| 3 | `fix/history-navigation` | `history.py`, `callbacks.py` | — | `test_history.py` |
| 4 | `fix/string-fixes` | `seed_strings.py`, `gift.py`, `divination.py` | `gift.cancelled` | `test_strings.py` |
| 5 | `feat/ux-additions` | `keyboards.py`, `menu.py`, `daily.py`, `divination.py`, `qa.py`, `seed_strings.py` | `btn.buy`, `daily.kb.close` | `test_pr5_ux.py` |

PRs are independent — no cross-branch dependencies. Recommended merge order: 1 → 2 → 3 → 4 → 5.
