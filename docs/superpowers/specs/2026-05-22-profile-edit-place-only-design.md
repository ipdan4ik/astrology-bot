# Profile-Edit "Place Only" — Design Spec

**Date:** 2026-05-22
**Status:** Approved (ready for implementation plan)
**Branch:** feat/profile-edit-place-only

## Goal

Make the profile-edit screen match onboarding: the user edits only the birth **place** (via
a Telegram location or typed text); coordinates and timezone are derived automatically and are
no longer separately editable or shown.

## Background — current profile edit

`src/quantuum/bot/handlers/profile.py` drives editing: `profile_kb` (in
`src/quantuum/bot/ui/keyboards.py`) renders one button per field from `_PROFILE_FIELDS`
(name, birth_date, birth_time, birth_place, **coords**, **timezone**). Tapping a button fires
`ProfileCb(action="edit", field=...)` → `on_edit_field` sets `ProfileEdit.awaiting_value` and
stores the field, prompting with `FIELD_PROMPT_KEYS[field]`. The next text message →
`on_edit_value` → `save_field` → `apply_field_edit(current, field, raw)` (in
`src/quantuum/bot/ui/profile_fields.py`, a pure sync validator) → `upsert_natal_profile`.

`render_profile` (in `src/quantuum/bot/ui/text.py`) currently prints title, name, birth_date,
birth_time, place, **coords**, **timezone**.

The just-merged geocoding feature provides `quantuum.geocoding.geocode(query) -> list[GeoResult]`,
`reverse(lat, lon) -> GeoResult | None`, `coords_to_timezone(lat, lon) -> str`, and
`GeoResult(lat, lon, display_name)`. Onboarding already uses this flow (location or typed +
confirm) but with hardcoded Russian strings. Profile-edit uses **i18n** (`Translator`), and this
feature keeps that — new strings go in `BASE_STRINGS` (ru + en).

## Changes

### 1. Profile view — show only the address (`text.py: render_profile`)

Remove the `profile.coords` and `profile.timezone` lines. New body: title, name, birth_date,
birth_time, place.

### 2. Edit keyboard — drop coords/timezone (`keyboards.py: _PROFILE_FIELDS`)

`_PROFILE_FIELDS` becomes:
```python
_PROFILE_FIELDS = [
    ("profile.kb.edit_name", "name"),
    ("profile.kb.edit_birth_date", "birth_date"),
    ("profile.kb.edit_birth_time", "birth_time"),
    ("profile.kb.edit_birth_place", "birth_place"),
]
```
`profile_kb` layout `b.adjust(2, 2, 2)` becomes `b.adjust(2, 2)`.

### 3. Editing "Место рождения" → onboarding-style flow (`profile.py`)

Extend `ProfileEdit` with two states:
```python
class ProfileEdit(StatesGroup):
    awaiting_value = State()   # name / birth_date / birth_time (text)
    awaiting_place = State()   # birth_place: location or typed text
    place_confirm = State()    # typed place awaiting Да / Другой адрес
```

`on_edit_field`: if `callback_data.field == "birth_place"` → set `ProfileEdit.awaiting_place`
and prompt `profile.prompt.birth_place`; otherwise the existing `awaiting_value` path.

New handlers (all use the injected `account: Account` and `i18n: Translator`):

- `on_edit_place_location` (`ProfileEdit.awaiting_place`, `F.location`):
  `lat/lon` from the message → `tz = coords_to_timezone(lat, lon)` →
  `geo = await reverse(lat, lon)` → `place = geo.display_name if geo else f"📍 {lat:.4f}, {lon:.4f}"`
  → `save_place(...)` → `state.clear()` → `show_profile`.
- `on_edit_place_text` (`ProfileEdit.awaiting_place`, `F.text`):
  `results = await geocode(text)`; empty → re-prompt with `profile.place.not_found`; else take
  `results[0]`, `tz = coords_to_timezone(...)`, store pending
  `{place, latitude, longitude, timezone}` in FSM, set `ProfileEdit.place_confirm`, send
  `profile.place.confirm` (param `place`, showing only the address) with an inline keyboard:
  Да = `ProfileCb(action="place_confirm")`, Другой адрес = `ProfileCb(action="place_retry")`.
- `on_edit_place_other` (`ProfileEdit.awaiting_place`, fallback): re-prompt
  `profile.prompt.birth_place`.
- `on_place_confirm` (`ProfileCb.filter(F.action == "place_confirm")`, `ProfileEdit.place_confirm`):
  read pending from FSM → `save_place(...)` → `state.clear()` → `show_profile`.
- `on_place_retry` (`ProfileCb.filter(F.action == "place_retry")`, `ProfileEdit.place_confirm`):
  set `ProfileEdit.awaiting_place`, re-prompt `profile.prompt.birth_place`.

`save_place(session, *, account, place, latitude, longitude, timezone)`: load the existing
profile (`get_natal_profile`); if None return `"profile.not_found"`; otherwise
`upsert_natal_profile(... **{**profile_to_kwargs(profile), "birth_place": place,
"latitude": Decimal(str(latitude)), "longitude": Decimal(str(longitude)),
"timezone": timezone})` — i.e. update only those four fields, keep the rest.

Handler-order note: register `F.location` then `F.text` then the bare fallback (aiogram matches
in order). The new place-confirm callbacks must be filtered on `ProfileEdit.place_confirm` so
stale buttons can't fire out of state.

### 4. `apply_field_edit` cleanup (`profile_fields.py`)

`apply_field_edit` keeps only `name`, `birth_date`, `birth_time`. Remove the `birth_place`,
`coords`, and `timezone` branches (birth_place now has its own flow). Delete the relocated
`parse_coords`, `is_valid_timezone`, `_valid_timezones` and their now-unused imports
(`Decimal`, `InvalidOperation`, `lru_cache`, `available_timezones`). `FIELD_PROMPT_KEYS` keeps
only `name`, `birth_date`, `birth_time` (birth_place is prompted by `on_edit_field` directly via
`profile.prompt.birth_place`).

### 5. i18n strings (`seed_strings.py: BASE_STRINGS`)

Repurpose:
```python
"profile.prompt.birth_place": {
    "ru": "Пришли геопозицию (📎 → Геопозиция) или напиши город / адрес:",
    "en": "Send your location (📎 → Location) or type a city / address:",
},
```
Add:
```python
"profile.place.confirm": {
    "ru": "Нашёл: {place}\n\nВерно?",
    "en": "Found: {place}\n\nCorrect?",
},
"profile.place.not_found": {
    "ru": "Не нашёл это место. Уточни город / адрес или пришли геопозицию:",
    "en": "Couldn't find that place. Refine the city / address or send a location:",
},
"profile.kb.place_confirm": {"ru": "✅ Да", "en": "✅ Yes"},
"profile.kb.place_retry": {"ru": "✏️ Другой адрес", "en": "✏️ Different address"},
```
Remove (now unused): `profile.coords`, `profile.timezone`, `profile.kb.edit_coords`,
`profile.kb.edit_timezone`, `profile.prompt.coords`, `profile.prompt.timezone`,
`profile.error.coords_invalid`, `profile.error.timezone_invalid`. Update the doc comment block
at the top of the file accordingly. (`ensure_base_strings` is insert-only — removing from the
source does not delete already-seeded rows; harmless. The repurposed `profile.prompt.birth_place`
text won't auto-update on already-seeded tenants — handled by a live i18n refresh at deploy.)

### 6. Callbacks (`callbacks.py`)

`ProfileCb` already has `action: str` + `field: str`; the new actions `place_confirm` /
`place_retry` need no structural change (document them in the comment).

## Error handling

- Geocode network/timeout/no-result → `profile.place.not_found`, stay in `awaiting_place`.
- `reverse` failure on the location path → fall back to `📍 lat, lon` display name; never blocks.
- `coords_to_timezone` always returns a valid IANA string (closest fallback).
- Stale confirm buttons: callbacks are state-filtered on `place_confirm`, so they no-op otherwise.
- A non-text/non-location message in `awaiting_place` → fallback re-prompt.

## Testing

- `render_profile` (`tests/test_ui_text.py`): asserts the rendered profile contains the place and
  does **not** contain the latitude/longitude/timezone values.
- `profile_kb` (`tests/test_ui_keyboards.py`): asserts the edit fields are exactly
  `{name, birth_date, birth_time, birth_place}` (no coords/timezone).
- `apply_field_edit` (`tests/test_ui_profile_fields.py`): keep name/date/time tests; remove the
  coords/timezone/birth_place tests (those branches are gone). Add an assertion that editing
  `coords`/`timezone`/`birth_place` via `apply_field_edit` returns the `unknown_field` error
  (they're no longer handled there).
- Profile place-edit handlers (`tests/test_profile_screen.py`, reuse the existing fake-state
  pattern; monkeypatch `geocode`/`reverse`/`coords_to_timezone` and `get_sessionmaker`/
  `save_place` as needed; **no real network**):
  - location → `save_place` called with derived tz; state cleared.
  - typed → confirm shown, state `place_confirm`, pending stored.
  - typed not-found → re-prompt, no save, state stays `awaiting_place`.
  - `place_confirm` callback → `save_place` called; state cleared.
  - `place_retry` callback → state back to `awaiting_place`.
  - `save_place` updates only the four fields, preserving name/date/time of the existing profile.

## Files

| File | Change |
|------|--------|
| `src/quantuum/bot/ui/text.py` | `render_profile`: drop coords + timezone lines |
| `src/quantuum/bot/ui/keyboards.py` | `_PROFILE_FIELDS`: drop coords/timezone; `adjust(2, 2)` |
| `src/quantuum/bot/handlers/profile.py` | place-edit FSM (location/typed/confirm/retry) + `save_place`; route birth_place in `on_edit_field` |
| `src/quantuum/bot/ui/profile_fields.py` | trim `apply_field_edit` + `FIELD_PROMPT_KEYS`; delete `parse_coords`/`is_valid_timezone` |
| `src/quantuum/i18n/seed_strings.py` | repurpose birth_place prompt; add place.confirm/not_found + kb.place_*; remove coords/timezone keys |
| `src/quantuum/bot/ui/callbacks.py` | document `place_confirm`/`place_retry` on `ProfileCb` |
| tests | `test_ui_text.py`, `test_ui_keyboards.py`, `test_ui_profile_fields.py`, `test_profile_screen.py` |

## Out of scope

- Changing onboarding's confirm wording (it keeps showing the timezone; only the profile view +
  edit-confirm hide it).
- Self-hosted Nominatim (later config swap).
- Migrating existing profiles.
