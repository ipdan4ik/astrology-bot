# Profile-Edit "Place Only" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The profile-edit screen edits only the birth place (Telegram location or typed text, like onboarding); coordinates and timezone are derived automatically and no longer shown or separately editable.

**Architecture:** Reuse the merged `quantuum.geocoding` module. The profile-edit FSM gains a place sub-flow (location / typed + confirm) that updates only place/lat/lon/timezone; the coords/timezone edit fields, their validators, and their profile-view lines are removed. All new user-facing strings are i18n (`BASE_STRINGS`, ru+en).

**Tech Stack:** Python 3.12, aiogram 3, SQLModel, pytest (asyncio auto mode).

**Branch:** `feat/profile-edit-place-only` (already checked out).

**Test environment:** Run from repo root with `uv run pytest`. Tests use the test PG/redis at 172.30.0.2 / 172.30.0.3 (wired in `tests/conftest.py`); the `conftest.build_translator(session, tenant_id, lang=...)` helper seeds `BASE_STRINGS` and returns a ready `Translator`. **No test may make a real geocoder/network call** — `geocode`/`reverse` are monkeypatched. The `warning: VIRTUAL_ENV=/usr ...` line is harmless. After each task run `uv run ruff check <changed files>`.

---

### Task 1: i18n strings for the place edit flow

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Test: `tests/test_i18n_seed.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_i18n_seed.py`:

```python
def test_place_edit_strings_present_and_obsolete_removed():
    from quantuum.i18n.seed_strings import BASE_STRINGS

    for key in [
        "profile.place.confirm",
        "profile.place.not_found",
        "profile.kb.place_confirm",
        "profile.kb.place_retry",
    ]:
        assert key in BASE_STRINGS, f"missing {key}"
        assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key]

    # The repurposed place prompt now mentions geolocation.
    assert "геопозиц" in BASE_STRINGS["profile.prompt.birth_place"]["ru"].lower()

    for key in [
        "profile.coords",
        "profile.timezone",
        "profile.kb.edit_coords",
        "profile.kb.edit_timezone",
        "profile.prompt.coords",
        "profile.prompt.timezone",
        "profile.error.coords_invalid",
        "profile.error.timezone_invalid",
    ]:
        assert key not in BASE_STRINGS, f"obsolete key still present: {key}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_i18n_seed.py::test_place_edit_strings_present_and_obsolete_removed -q`
Expected: FAIL (new keys missing / obsolete keys still present).

- [ ] **Step 3: Edit `src/quantuum/i18n/seed_strings.py`**

(a) Replace the `profile.prompt.birth_place` entry with:
```python
    "profile.prompt.birth_place": {
        "ru": "Пришли геопозицию (📎 → Геопозиция) или напиши город / адрес:",
        "en": "Send your location (📎 → Location) or type a city / address:",
    },
```

(b) DELETE these entries entirely: `profile.coords`, `profile.timezone`, `profile.kb.edit_coords`, `profile.kb.edit_timezone`, `profile.prompt.coords`, `profile.prompt.timezone`, `profile.error.coords_invalid`, `profile.error.timezone_invalid`. Also remove their lines from the doc comment block near the top of the file (the `profile.coords — {lat}, {lon}` etc. reference lines).

(c) Add these new entries (place them near the other `profile.*` entries):
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_i18n_seed.py -q`
Expected: PASS. Also `uv run python -c "import quantuum.i18n.seed_strings"` → no error.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py tests/test_i18n_seed.py
git commit -m "feat(profile): i18n strings for place edit; drop coords/timezone keys"
```

---

### Task 2: Profile view shows only the address

**Files:**
- Modify: `src/quantuum/bot/ui/text.py`
- Test: `tests/test_ui_text.py`

- [ ] **Step 1: Update the tests** — in `tests/test_ui_text.py`:

Replace `test_render_profile_contains_fields_ru` with:
```python
async def test_render_profile_contains_fields_ru(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    rendered = await text.render_profile(i18n, _Profile())
    assert "👤 Твой профиль:" in rendered
    assert "Имя: Anna" in rendered
    assert "Дата рождения: 1980-06-24" in rendered
    assert "Время: 10:00" in rendered
    assert "Место: Moscow" in rendered
    # Coordinates and timezone are no longer shown.
    assert "55.7558" not in rendered
    assert "Europe/Moscow" not in rendered
```

Replace `test_render_profile_uses_lang` with:
```python
async def test_render_profile_uses_lang(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id, lang="en")
    rendered = await text.render_profile(i18n, _Profile())
    assert "👤 Your profile:" in rendered
    assert "Name: Anna" in rendered
    assert "Europe/Moscow" not in rendered  # timezone hidden
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_text.py -k render_profile -q`
Expected: FAIL (coords/timezone still rendered).

- [ ] **Step 3: Edit `render_profile` in `src/quantuum/bot/ui/text.py`**

Remove the `profile.coords` and `profile.timezone` lines so the body is:
```python
async def render_profile(i18n: Translator, profile) -> str:
    lines = [
        await i18n("profile.title"),
        "",
        await i18n("profile.name", name=profile.full_name),
        await i18n("profile.birth_date", birth_date=profile.birth_date.isoformat()),
        await i18n("profile.birth_time", birth_time=profile.birth_time.strftime("%H:%M")),
        await i18n("profile.place", place=profile.birth_place),
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui_text.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/ui/text.py tests/test_ui_text.py
git commit -m "feat(profile): show only the address in the profile view"
```

---

### Task 3: Edit keyboard drops coords/timezone

**Files:**
- Modify: `src/quantuum/bot/ui/keyboards.py`
- Test: `tests/test_ui_keyboards.py`

- [ ] **Step 1: Update the test** — replace `test_profile_kb_with_profile_has_field_edit_buttons` in `tests/test_ui_keyboards.py`:

```python
async def test_profile_kb_with_profile_has_field_edit_buttons(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    kb = await profile_kb(has_profile=True, i18n=i18n)
    fields = {ProfileCb.unpack(b.callback_data).field for b in _inline(kb)}
    assert fields == {"name", "birth_date", "birth_time", "birth_place"}
    labels = {b.text for b in _inline(kb)}
    assert "✏️ Имя" in labels
    assert "✏️ Таймзона" not in labels  # timezone no longer editable
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_keyboards.py -k profile_kb -q`
Expected: FAIL (coords/timezone fields still present).

- [ ] **Step 3: Edit `src/quantuum/bot/ui/keyboards.py`**

Replace `_PROFILE_FIELDS` with:
```python
_PROFILE_FIELDS = [
    ("profile.kb.edit_name", "name"),
    ("profile.kb.edit_birth_date", "birth_date"),
    ("profile.kb.edit_birth_time", "birth_time"),
    ("profile.kb.edit_birth_place", "birth_place"),
]
```
In `profile_kb`, change `b.adjust(2, 2, 2)` to `b.adjust(2, 2)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui_keyboards.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/ui/keyboards.py tests/test_ui_keyboards.py
git commit -m "feat(profile): drop coords/timezone edit buttons"
```

---

### Task 4: Place-edit FSM + `save_place` in the profile handler

**Files:**
- Modify: `src/quantuum/bot/handlers/profile.py`
- Test: `tests/test_profile_screen.py`

Read `src/quantuum/bot/handlers/profile.py` first.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_profile_screen.py`:

```python
class _FakeState:
    def __init__(self, data):
        self._data = dict(data)
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, s):
        self.state = s

    async def clear(self):
        self._data = {}
        self.state = None


def _patch_sessionmaker(monkeypatch, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    import quantuum.bot.handlers.profile as pr

    monkeypatch.setattr(pr, "get_sessionmaker", lambda: _Maker())


async def test_save_place_updates_only_place_fields(session, default_tenant):
    from decimal import Decimal

    from quantuum.bot.handlers.profile import save_place

    acc = await _acc_with_profile(session, default_tenant.id)
    err = await save_place(
        session, account=acc, place="Bratsk, Russia",
        latitude=56.13, longitude=101.61, timezone="Asia/Irkutsk",
    )
    assert err is None
    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_place == "Bratsk, Russia"
    assert profile.timezone == "Asia/Irkutsk"
    assert profile.latitude == Decimal("56.13")
    assert profile.full_name == "Anna"  # untouched
    assert profile.birth_time == time(10, 0)  # untouched


async def test_edit_place_location_updates_profile(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.geocoding import GeoResult

    acc = await _acc_with_profile(session, default_tenant.id)
    _patch_sessionmaker(monkeypatch, session)
    monkeypatch.setattr(pr, "coords_to_timezone", lambda lat, lon: "Asia/Irkutsk")
    monkeypatch.setattr(pr, "reverse", AsyncMock(return_value=GeoResult(56.13, 101.61, "Bratsk, Russia")))
    monkeypatch.setattr(pr, "show_profile", AsyncMock())

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    state.state = pr.ProfileEdit.awaiting_place
    message = SimpleNamespace(
        location=SimpleNamespace(latitude=56.13, longitude=101.61), answer=AsyncMock()
    )

    await pr.on_edit_place_location(message, state, account=acc, i18n=i18n)

    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_place == "Bratsk, Russia"
    assert profile.timezone == "Asia/Irkutsk"
    assert state.state is None
    pr.show_profile.assert_awaited_once()


async def test_edit_place_text_geocodes_then_confirms(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.geocoding import GeoResult

    monkeypatch.setattr(
        pr, "geocode", AsyncMock(return_value=[GeoResult(56.13, 101.61, "Bratsk, Russia")])
    )
    monkeypatch.setattr(pr, "coords_to_timezone", lambda lat, lon: "Asia/Irkutsk")

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    state.state = pr.ProfileEdit.awaiting_place
    message = SimpleNamespace(text="Bratsk", answer=AsyncMock())

    await pr.on_edit_place_text(message, state, i18n=i18n)

    assert state.state == pr.ProfileEdit.place_confirm
    data = await state.get_data()
    assert data["place"] == "Bratsk, Russia" and data["timezone"] == "Asia/Irkutsk"
    text_out = message.answer.await_args.args[0]
    assert "Bratsk, Russia" in text_out


async def test_edit_place_text_not_found_reprompts(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr

    monkeypatch.setattr(pr, "geocode", AsyncMock(return_value=[]))

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    state.state = pr.ProfileEdit.awaiting_place
    message = SimpleNamespace(text="asdfghjkl", answer=AsyncMock())

    await pr.on_edit_place_text(message, state, i18n=i18n)

    assert state.state == pr.ProfileEdit.awaiting_place  # unchanged
    message.answer.assert_awaited()


async def test_place_confirm_saves(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.bot.ui.callbacks import ProfileCb

    acc = await _acc_with_profile(session, default_tenant.id)
    _patch_sessionmaker(monkeypatch, session)
    monkeypatch.setattr(pr, "show_profile", AsyncMock())

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState(
        {"place": "Bratsk, Russia", "latitude": "56.13", "longitude": "101.61", "timezone": "Asia/Irkutsk"}
    )
    state.state = pr.ProfileEdit.place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())

    await pr.on_place_confirm(query, ProfileCb(action="place_confirm"), state, account=acc, i18n=i18n)

    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_place == "Bratsk, Russia"
    assert state.state is None


async def test_place_retry_returns_to_awaiting_place(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.bot.ui.callbacks import ProfileCb

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({"place": "x"})
    state.state = pr.ProfileEdit.place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())

    await pr.on_place_retry(query, ProfileCb(action="place_retry"), state, i18n=i18n)

    assert state.state == pr.ProfileEdit.awaiting_place
```

(Add `from .conftest import build_translator` to the test file's imports if not present, and ensure `time`/`get_natal_profile` are imported — they already are.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_profile_screen.py -q`
Expected: the new tests FAIL (`save_place`/`on_edit_place_*`/`ProfileEdit.awaiting_place` don't exist).

- [ ] **Step 3: Edit `src/quantuum/bot/handlers/profile.py`**

(a) Update imports — add at the top with the existing imports:
```python
from decimal import Decimal

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.geocoding import coords_to_timezone, geocode, reverse
```

(b) Replace the `ProfileEdit` state group with:
```python
class ProfileEdit(StatesGroup):
    awaiting_value = State()  # name / birth_date / birth_time (text)
    awaiting_place = State()  # birth_place: location or typed text
    place_confirm = State()  # typed place awaiting Да / Другой адрес
```

(c) Add `save_place` after `save_field`:
```python
async def save_place(
    session, *, account: Account, place: str, latitude, longitude, timezone: str
) -> str | None:
    """Update only the place + derived coordinates/timezone of the existing profile.

    Returns None on success, or an i18n error key.
    """
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "profile.not_found"
    kwargs = profile_to_kwargs(profile)
    kwargs.update(
        birth_place=place,
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        timezone=timezone,
    )
    await upsert_natal_profile(
        session, tenant_id=account.tenant_id, account_id=account.id, **kwargs
    )
    return None
```

(d) Replace `on_edit_field` with a version that routes birth_place to the place sub-flow:
```python
@router.callback_query(ProfileCb.filter(F.action == "edit"))
async def on_edit_field(
    query: CallbackQuery, callback_data: ProfileCb, state: FSMContext, i18n: Translator
) -> None:
    field = callback_data.field
    if field == "birth_place":
        await state.set_state(ProfileEdit.awaiting_place)
        await query.message.answer(
            await i18n("profile.prompt.birth_place"), reply_markup=await cancel_kb(i18n)
        )
        await query.answer()
        return
    await state.set_state(ProfileEdit.awaiting_value)
    await state.update_data(field=field)
    await query.message.answer(
        await i18n(FIELD_PROMPT_KEYS[field]), reply_markup=await cancel_kb(i18n)
    )
    await query.answer()
```

(e) Add the place sub-flow handlers (place them after `on_edit_value`):
```python
async def place_confirm_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_confirm"),
            callback_data=ProfileCb(action="place_confirm").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_retry"),
            callback_data=ProfileCb(action="place_retry").pack(),
        )
    )
    return builder.as_markup()


@router.message(ProfileEdit.awaiting_place, F.location)
async def on_edit_place_location(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    tz = coords_to_timezone(lat, lon)
    geo = await reverse(lat, lon)
    place = geo.display_name if geo is not None else f"📍 {lat:.4f}, {lon:.4f}"
    async with get_sessionmaker()() as session:
        err_key = await save_place(
            session, account=account, place=place, latitude=lat, longitude=lon, timezone=tz
        )
    if err_key is not None:
        await message.answer(await i18n(err_key))
        return
    await state.clear()
    await show_profile(message, account, i18n)


@router.message(ProfileEdit.awaiting_place, F.text)
async def on_edit_place_text(message: Message, state: FSMContext, i18n: Translator) -> None:
    results = await geocode((message.text or "").strip())
    if not results:
        await message.answer(
            await i18n("profile.place.not_found"), reply_markup=await cancel_kb(i18n)
        )
        return
    top = results[0]
    tz = coords_to_timezone(top.lat, top.lon)
    await state.update_data(
        place=top.display_name, latitude=str(top.lat), longitude=str(top.lon), timezone=tz
    )
    await state.set_state(ProfileEdit.place_confirm)
    await message.answer(
        await i18n("profile.place.confirm", place=top.display_name),
        reply_markup=await place_confirm_kb(i18n),
    )


@router.message(ProfileEdit.awaiting_place)
async def on_edit_place_other(message: Message, i18n: Translator) -> None:
    await message.answer(
        await i18n("profile.prompt.birth_place"), reply_markup=await cancel_kb(i18n)
    )


@router.callback_query(ProfileCb.filter(F.action == "place_confirm"), ProfileEdit.place_confirm)
async def on_place_confirm(
    query: CallbackQuery, callback_data: ProfileCb, state: FSMContext,
    account: Account, i18n: Translator,
) -> None:
    data = await state.get_data()
    async with get_sessionmaker()() as session:
        err_key = await save_place(
            session, account=account, place=data["place"],
            latitude=data["latitude"], longitude=data["longitude"], timezone=data["timezone"],
        )
    await query.answer()
    if err_key is not None:
        await query.message.answer(await i18n(err_key))
        return
    await state.clear()
    await show_profile(query.message, account, i18n)


@router.callback_query(ProfileCb.filter(F.action == "place_retry"), ProfileEdit.place_confirm)
async def on_place_retry(
    query: CallbackQuery, callback_data: ProfileCb, state: FSMContext, i18n: Translator
) -> None:
    await state.set_state(ProfileEdit.awaiting_place)
    await query.message.answer(
        await i18n("profile.prompt.birth_place"), reply_markup=await cancel_kb(i18n)
    )
    await query.answer()
```

Register order: aiogram matches in source order, so `on_edit_place_location` (F.location) and `on_edit_place_text` (F.text) must appear before the bare `on_edit_place_other`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_profile_screen.py -q`
Expected: PASS. Also `uv run python -c "import quantuum.bot.handlers.profile"` → no error.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src/quantuum/bot/handlers/profile.py tests/test_profile_screen.py` (fix issues).
```bash
git add src/quantuum/bot/handlers/profile.py tests/test_profile_screen.py
git commit -m "feat(profile): edit birth place via location/typed geocoding (confirm)"
```

---

### Task 5: Trim `apply_field_edit` and delete the dead validators

**Files:**
- Modify: `src/quantuum/bot/ui/profile_fields.py`
- Test: `tests/test_ui_profile_fields.py`

- [ ] **Step 1: Update the tests** — in `tests/test_ui_profile_fields.py`:

Replace `test_prompt_keys_cover_all_fields` with:
```python
def test_prompt_keys_cover_text_fields_only():
    assert set(FIELD_PROMPT_KEYS) == {"name", "birth_date", "birth_time"}
    assert FIELD_PROMPT_KEYS["name"] == "profile.prompt.name"
```

DELETE these tests (their branches are gone): `test_edit_coords_updates_both`,
`test_edit_timezone_invalid_returns_error_key`, `test_edit_coords_out_of_range_rejected`,
`test_edit_timezone_directory_zone_rejected`.

ADD:
```python
def test_removed_fields_return_unknown_field():
    # coords / timezone / birth_place are no longer handled here (place has its own flow).
    for field in ("coords", "timezone", "birth_place"):
        updated, err_key = apply_field_edit(_base(), field, "whatever")
        assert updated is None
        assert err_key == "profile.error.unknown_field"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui_profile_fields.py -q`
Expected: FAIL (`FIELD_PROMPT_KEYS` still has extra keys; coords/timezone still handled).

- [ ] **Step 3: Edit `src/quantuum/bot/ui/profile_fields.py`**

Replace the ENTIRE file with:
```python
from quantuum.bot.handlers.onboarding import parse_birth_date, parse_birth_time

# field name -> i18n prompt key (resolved by the handler via the Translator).
# birth_place is handled by its own geocoding sub-flow, not via apply_field_edit.
FIELD_PROMPT_KEYS = {
    "name": "profile.prompt.name",
    "birth_date": "profile.prompt.birth_date",
    "birth_time": "profile.prompt.birth_time",
}


def apply_field_edit(current: dict, field: str, raw: str) -> tuple[dict | None, str | None]:
    """Return (updated_profile_kwargs, None) on success, or (None, error_key) on
    invalid input. `current` holds the full upsert kwargs of the existing profile.

    Only the free-text fields are handled here; birth place (with derived coordinates
    and timezone) goes through the geocoding sub-flow in the profile handler.
    """
    updated = dict(current)
    raw = raw.strip()
    if field == "name":
        if not raw:
            return None, "profile.error.name_empty"
        updated["full_name"] = raw
    elif field == "birth_date":
        parsed = parse_birth_date(raw)
        if parsed is None:
            return None, "profile.error.birth_date_invalid"
        updated["birth_date"] = parsed
    elif field == "birth_time":
        parsed = parse_birth_time(raw)
        if parsed is None:
            return None, "profile.error.birth_time_invalid"
        updated["birth_time"] = parsed
    else:
        return None, "profile.error.unknown_field"
    return updated, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui_profile_fields.py -q`
Expected: PASS. Also `uv run python -c "import quantuum.bot.ui.profile_fields"` → no error.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src/quantuum/bot/ui/profile_fields.py tests/test_ui_profile_fields.py`
```bash
git add src/quantuum/bot/ui/profile_fields.py tests/test_ui_profile_fields.py
git commit -m "refactor(profile): trim apply_field_edit to text fields; drop coords/tz validators"
```

---

### Task 6: Full suite + lint gate

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 3: Commit (only if ruff auto-fixed anything)**

```bash
git add -A && git commit -m "chore(profile): lint" || echo "nothing to commit"
```

---

## Manual verification (after merge + i18n refresh)

`ensure_base_strings` is insert-only, so the **repurposed** `profile.prompt.birth_place` text will not auto-update on already-seeded tenants. After rebuilding the stack
(`docker compose -f docker-compose.yml -f docker-compose.polling.yml up -d --build`), refresh the live strings:
- Update the changed row + invalidate the i18n cache (a one-off: re-run the seed with an update path, or `UPDATE platform_strings SET value=... WHERE key='profile.prompt.birth_place'` then `invalidate_i18n_all()`), then verify in a tenant bot:
  1. `/profile` → the view shows only name/date/time/place (no coords/timezone).
  2. Tap **Место рождения** → send a location → profile updates, coords/tz derived.
  3. Tap **Место рождения** → type a city → "Нашёл: … — Верно?" → Да → updated.

## Out of scope

- Changing onboarding's confirm wording (still shows timezone there).
- Migrating existing profiles; self-hosted Nominatim.
