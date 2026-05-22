# Birth-Place Geocoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboarding asks only for a city/location; the backend derives latitude, longitude, and IANA timezone automatically.

**Architecture:** A new `quantuum.geocoding` module resolves a place to coordinates (Nominatim over httpx) and coordinates to a timezone (timezonefinder, offline). The onboarding birth-place step accepts either a Telegram location (exact → save) or typed text (geocode → confirm → save), replacing the old coordinate and timezone entry steps.

**Tech Stack:** Python 3.12, aiogram 3, SQLModel, httpx (already a dep), timezonefinder (new), pytest (asyncio auto mode).

**Branch:** `feat/birth-place-geocoding` (already checked out).

**Test environment:** Run from repo root with `uv run pytest`. Tests use the test PG/redis at 172.30.0.2 / 172.30.0.3 (wired in `tests/conftest.py`). **No test may make a real Nominatim/network call** — all geocode/reverse HTTP is mocked. The `warning: VIRTUAL_ENV=/usr ...` line in output is harmless. After each task run `uv run ruff check <changed files>` and fix issues.

**Conventions:**
- Fixtures: `session` (AsyncSession), `default_tenant` (a `Tenant` slug `default`).
- Onboarding handlers use hardcoded Russian strings (no i18n) — match that style.
- `account: Account` is injected by middleware into both message and callback handlers.

---

### Task 1: Geocoding module — `GeoResult` + `coords_to_timezone` (+ timezonefinder dep)

**Files:**
- Modify: `pyproject.toml` (add dependency)
- Create: `src/quantuum/geocoding.py`
- Test: `tests/test_geocoding.py`

- [ ] **Step 1: Add the dependency**

Run: `uv add timezonefinder`
Expected: `pyproject.toml` gains `timezonefinder` under dependencies and `uv.lock` updates. Verify import works:
`uv run python -c "from timezonefinder import TimezoneFinder; print(TimezoneFinder().timezone_at(lat=55.75, lng=37.62))"`
Expected output: `Europe/Moscow`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_geocoding.py
def test_coords_to_timezone_known_cities():
    from quantuum.geocoding import coords_to_timezone

    assert coords_to_timezone(55.7558, 37.6173) == "Europe/Moscow"
    assert coords_to_timezone(52.52, 13.405) == "Europe/Berlin"


def test_coords_to_timezone_returns_str_for_ocean_like_point():
    # A point far at sea still resolves to some IANA zone (closest), never crashes.
    from quantuum.geocoding import coords_to_timezone

    tz = coords_to_timezone(0.0, -160.0)
    assert isinstance(tz, str) and tz
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_geocoding.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'quantuum.geocoding'`

- [ ] **Step 4: Create the module**

```python
# src/quantuum/geocoding.py
from dataclasses import dataclass

from timezonefinder import TimezoneFinder

from quantuum.logging_setup import get_logger

logger = get_logger("geocoding")

_tf = TimezoneFinder()


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lon: float
    display_name: str


def coords_to_timezone(lat: float, lon: float) -> str:
    """IANA timezone for coordinates (offline, deterministic).

    Falls back to the closest zone for edge/coastal points; "UTC" only as a last resort.
    """
    tz = _tf.timezone_at(lat=lat, lng=lon)
    if tz is None:
        tz = _tf.closest_timezone_at(lat=lat, lng=lon)
    return tz or "UTC"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_geocoding.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/quantuum/geocoding.py tests/test_geocoding.py
git commit -m "feat(geocoding): coords_to_timezone via timezonefinder + GeoResult"
```

---

### Task 2: `geocode` + `reverse` (Nominatim over httpx)

**Files:**
- Modify: `src/quantuum/geocoding.py`
- Modify: `src/quantuum/settings.py` (the module reads `geocoder_url`/`geocoder_user_agent`; they are added in Task 3, so this task references `get_settings()` — Task 3 adds the fields. To keep this task self-contained and runnable, add the two settings fields here as part of Step 3 if they are not yet present.)
- Test: `tests/test_geocoding.py`

> Note: Tasks 2 and 3 both touch settings. Implement the two settings fields in whichever runs first; the other task then finds them already present. The plan lists them in Task 3 for clarity, but `geocode`/`reverse` need them — so add the fields in this task if missing.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_geocoding.py
import httpx


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, data=None, error=None):
        self._data = data
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if self._error is not None:
            raise self._error
        return _FakeResp(self._data)


async def test_geocode_parses_results(monkeypatch):
    from quantuum import geocoding

    payload = [
        {"lat": "55.7558", "lon": "37.6173", "display_name": "Moscow, Russia"},
        {"lat": "46.35", "lon": "-94.0", "display_name": "Moscow, Latah County, Idaho, USA"},
    ]
    monkeypatch.setattr(geocoding.httpx, "AsyncClient", lambda **kw: _FakeClient(data=payload))

    results = await geocoding.geocode("Moscow", limit=2)
    assert results[0] == geocoding.GeoResult(55.7558, 37.6173, "Moscow, Russia")
    assert len(results) == 2


async def test_geocode_empty_query_returns_empty():
    from quantuum import geocoding

    assert await geocoding.geocode("   ") == []


async def test_geocode_network_error_returns_empty(monkeypatch):
    from quantuum import geocoding

    monkeypatch.setattr(
        geocoding.httpx,
        "AsyncClient",
        lambda **kw: _FakeClient(error=httpx.ConnectError("boom")),
    )
    assert await geocoding.geocode("Moscow") == []


async def test_reverse_parses_or_none(monkeypatch):
    from quantuum import geocoding

    monkeypatch.setattr(
        geocoding.httpx,
        "AsyncClient",
        lambda **kw: _FakeClient(data={"lat": "55.75", "lon": "37.62", "display_name": "Moscow"}),
    )
    got = await geocoding.reverse(55.75, 37.62)
    assert got == geocoding.GeoResult(55.75, 37.62, "Moscow")

    monkeypatch.setattr(
        geocoding.httpx, "AsyncClient", lambda **kw: _FakeClient(data={"error": "Unable to geocode"})
    )
    assert await geocoding.reverse(0.0, 0.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geocoding.py -k "geocode or reverse" -q`
Expected: FAIL — `AttributeError: module 'quantuum.geocoding' has no attribute 'httpx'` (or `geocode`/`reverse` undefined)

- [ ] **Step 3: Implement geocode/reverse (and ensure settings fields exist)**

Ensure `src/quantuum/settings.py` has these two fields on the `Settings` class (add if not present — Task 3 also lists them):

```python
    geocoder_url: str = "https://nominatim.openstreetmap.org"
    geocoder_user_agent: str = "quantuum-bot (onboarding geocoder)"
```

Add to `src/quantuum/geocoding.py` (new imports at the top with the existing ones):

```python
import httpx

from quantuum.settings import get_settings

_TIMEOUT = httpx.Timeout(10.0)


def _headers() -> dict[str, str]:
    return {"User-Agent": get_settings().geocoder_user_agent}


async def geocode(query: str, *, limit: int = 1) -> list[GeoResult]:
    """Forward-geocode free text via a Nominatim-compatible endpoint.

    Returns [] on empty query or any network/HTTP error (caller re-prompts).
    """
    q = (query or "").strip()
    if not q:
        return []
    url = f"{get_settings().geocoder_url}/search"
    params = {"q": q, "format": "jsonv2", "limit": limit, "accept-language": "ru"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("geocode_failed", query=q)
        return []
    return [
        GeoResult(float(o["lat"]), float(o["lon"]), o["display_name"])
        for o in data
        if "lat" in o and "lon" in o
    ]


async def reverse(lat: float, lon: float) -> GeoResult | None:
    """Reverse-geocode coordinates to a display name. None on failure/no result."""
    url = f"{get_settings().geocoder_url}/reverse"
    params = {"lat": lat, "lon": lon, "format": "jsonv2", "accept-language": "ru"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("reverse_failed", lat=lat, lon=lon)
        return None
    if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
        return None
    return GeoResult(float(data["lat"]), float(data["lon"]), data.get("display_name", ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_geocoding.py -q`
Expected: PASS (all geocoding tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/geocoding.py src/quantuum/settings.py tests/test_geocoding.py
git commit -m "feat(geocoding): Nominatim geocode + reverse over httpx"
```

---

### Task 3: Settings fields (assert defaults)

**Files:**
- Modify: `src/quantuum/settings.py` (only if Task 2 didn't already add the fields)
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_settings.py
def test_geocoder_settings_defaults():
    from quantuum.settings import Settings

    assert Settings.model_fields["geocoder_url"].default == "https://nominatim.openstreetmap.org"
    assert Settings.model_fields["geocoder_user_agent"].default == "quantuum-bot (onboarding geocoder)"
```

- [ ] **Step 2: Run test to verify it fails (or passes if Task 2 added the fields)**

Run: `uv run pytest tests/test_settings.py::test_geocoder_settings_defaults -q`
Expected: PASS if Task 2 added the fields; otherwise FAIL with `KeyError` — then add the two fields to `Settings` (see Task 2 Step 3) and re-run.

- [ ] **Step 3: Commit (if anything changed)**

```bash
git add src/quantuum/settings.py tests/test_settings.py
git commit -m "feat(geocoding): geocoder_url + geocoder_user_agent settings" || echo "already committed in Task 2"
```

---

### Task 4: Onboarding birth-place flow (location / typed + confirm)

**Files:**
- Modify: `src/quantuum/bot/handlers/onboarding.py`
- Test: `tests/test_bot_onboarding.py`

This replaces the coordinate + timezone steps. Read the current `onboarding.py` first.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_onboarding.py`:

```python
class _State:
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


def _patch_sessionmaker(monkeypatch, mod):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(mod, "get_sessionmaker", lambda: _Maker())


_BASE = {"full_name": "Anna", "birth_date": "1980-06-24", "birth_time": "10:00"}


async def test_birth_place_location_saves_with_derived_tz(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.geocoding import GeoResult

    _patch_sessionmaker(monkeypatch, ob)
    saved = AsyncMock()
    monkeypatch.setattr(ob, "save_collected_profile", saved)
    monkeypatch.setattr(ob, "coords_to_timezone", lambda lat, lon: "Europe/Moscow")
    monkeypatch.setattr(ob, "reverse", AsyncMock(return_value=GeoResult(55.75, 37.62, "Moscow, Russia")))

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(
        location=SimpleNamespace(latitude=55.75, longitude=37.62), answer=AsyncMock()
    )
    account = SimpleNamespace(id=1, tenant_id=default_tenant.id)

    await ob.on_birth_place_location(message, state, account=account)

    saved.assert_awaited_once()
    data = saved.await_args.kwargs["data"]
    assert data["timezone"] == "Europe/Moscow"
    assert str(data["latitude"]) == "55.75"
    assert state.state is None  # cleared


async def test_birth_place_text_geocodes_then_confirms(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.geocoding import GeoResult

    monkeypatch.setattr(
        ob, "geocode", AsyncMock(return_value=[GeoResult(56.13, 101.61, "Bratsk, Russia")])
    )
    monkeypatch.setattr(ob, "coords_to_timezone", lambda lat, lon: "Asia/Irkutsk")

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(text="Bratsk", answer=AsyncMock())

    await ob.on_birth_place_text(message, state)

    assert state.state == ob.Onboarding.birth_place_confirm
    assert (await state.get_data())["timezone"] == "Asia/Irkutsk"
    text = message.answer.await_args.args[0]
    assert "Bratsk" in text and "Asia/Irkutsk" in text


async def test_birth_place_text_not_found_reprompts(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    monkeypatch.setattr(ob, "geocode", AsyncMock(return_value=[]))

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(text="asdfghjkl", answer=AsyncMock())

    await ob.on_birth_place_text(message, state)

    assert state.state == ob.Onboarding.birth_place  # unchanged, re-prompt
    message.answer.assert_awaited()


async def test_geo_confirm_saves(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.bot.ui.callbacks import OnboardCb

    _patch_sessionmaker(monkeypatch, ob)
    saved = AsyncMock()
    monkeypatch.setattr(ob, "save_collected_profile", saved)

    state = _State(
        {**_BASE, "birth_place": "Bratsk, Russia", "latitude": "56.13",
         "longitude": "101.61", "timezone": "Asia/Irkutsk"}
    )
    state.state = ob.Onboarding.birth_place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    account = SimpleNamespace(id=1, tenant_id=default_tenant.id)

    await ob.on_geo_confirm(query, OnboardCb(action="geo_confirm"), state, account=account)

    saved.assert_awaited_once()
    assert state.state is None


async def test_geo_retry_returns_to_birth_place(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.bot.ui.callbacks import OnboardCb

    state = _State({**_BASE})
    state.state = ob.Onboarding.birth_place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())

    await ob.on_geo_retry(query, OnboardCb(action="geo_retry"), state)

    assert state.state == ob.Onboarding.birth_place
```

Also DELETE these now-obsolete tests from `tests/test_bot_onboarding.py` (their code is being removed): `test_parse_coords_valid`, `test_parse_coords_invalid`, `test_parse_coords_rejects_out_of_range`, `test_is_valid_timezone`, `test_is_valid_timezone_rejects_directory_only_zone`, `test_is_valid_timezone_handles_blank_and_none`, `test_on_timezone_invalid_is_not_recorded`, and the `parse_coords` import on line 5. Keep the `parse_birth_date`/`parse_birth_time`/`parse_required_text`/`build_profile_data`/`save_collected_profile` tests. Update the top import line to: `from quantuum.bot.handlers.onboarding import parse_birth_date, parse_birth_time` (and `parse_required_text` is imported inside its own test already).

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `uv run pytest tests/test_bot_onboarding.py -q`
Expected: the new `test_birth_place_*` / `test_geo_*` tests FAIL (handlers/`birth_place_confirm` don't exist yet); collection may also error on the removed-symbol import until Step 3.

- [ ] **Step 3: Rewrite the onboarding module**

In `src/quantuum/bot/handlers/onboarding.py`:

(a) Replace the imports block at the top with:

```python
from datetime import date, datetime, time
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import OnboardCb
from quantuum.bot.ui.keyboards import cancel_kb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.geocoding import coords_to_timezone, geocode, reverse
```

(b) Replace the `Onboarding` state group with:

```python
class Onboarding(StatesGroup):
    full_name = State()
    birth_date = State()
    birth_time = State()
    birth_place = State()
    birth_place_confirm = State()
```

(c) DELETE the functions `parse_coords`, `is_valid_timezone`, and `_valid_timezones` (and the now-unused `lru_cache`/`available_timezones`/`InvalidOperation` imports — already removed in (a)). Keep `parse_required_text`, `parse_birth_date`, `parse_birth_time`, `build_profile_data`, `save_collected_profile`.

(d) Change `on_birth_time` so it transitions into the new birth_place prompt:

```python
@router.message(Onboarding.birth_time)
async def on_birth_time(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_time(message.text)
    if parsed is None:
        await message.answer("Не понял время. Формат ЧЧ:ММ:")
        return
    await state.update_data(birth_time=parsed.isoformat())
    await state.set_state(Onboarding.birth_place)
    await message.answer(
        "Место рождения: пришли геопозицию (📎 → Геопозиция, можно поставить точку на карте) "
        "или напиши город / часть адреса:"
    )
```

(e) DELETE the old `on_birth_place`, `on_coords`, and `on_timezone` handlers, and add this block in their place:

```python
async def geo_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=OnboardCb(action="geo_confirm").pack())
    )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Другой адрес", callback_data=OnboardCb(action="geo_retry").pack()
        )
    )
    return builder.as_markup()


async def _finalize_profile(state: FSMContext, account: Account) -> None:
    raw = await state.get_data()
    data = build_profile_data(raw, raw["timezone"])
    async with get_sessionmaker()() as session:
        await save_collected_profile(session, account=account, data=data)
    await state.clear()


_DONE_MSG = "Готово! Профиль сохранён. Команда /blueprint сгенерирует твой разбор."


@router.message(Onboarding.birth_place, F.location)
async def on_birth_place_location(message: Message, state: FSMContext, account: Account) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    tz = coords_to_timezone(lat, lon)
    geo = await reverse(lat, lon)
    display = geo.display_name if geo is not None else f"📍 {lat:.4f}, {lon:.4f}"
    await state.update_data(
        birth_place=display, latitude=str(lat), longitude=str(lon), timezone=tz
    )
    await _finalize_profile(state, account)
    await message.answer(_DONE_MSG)


@router.message(Onboarding.birth_place, F.text)
async def on_birth_place_text(message: Message, state: FSMContext) -> None:
    results = await geocode((message.text or "").strip())
    if not results:
        await message.answer("Не нашёл это место. Уточни город/адрес или пришли геопозицию:")
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
        f"Нашёл: {top.display_name}\nЧасовой пояс: {tz}\n\nВерно?",
        reply_markup=await geo_confirm_kb(),
    )


@router.message(Onboarding.birth_place)
async def on_birth_place_other(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пришли геопозицию (📎 → Геопозиция) или напиши город / адрес текстом:"
    )


@router.callback_query(OnboardCb.filter(F.action == "geo_confirm"), Onboarding.birth_place_confirm)
async def on_geo_confirm(
    query: CallbackQuery, callback_data: OnboardCb, state: FSMContext, account: Account
) -> None:
    await _finalize_profile(state, account)
    await query.message.answer(_DONE_MSG)
    await query.answer()


@router.callback_query(OnboardCb.filter(F.action == "geo_retry"))
async def on_geo_retry(query: CallbackQuery, callback_data: OnboardCb, state: FSMContext) -> None:
    await state.set_state(Onboarding.birth_place)
    await query.message.answer("Пришли геопозицию или другой город / адрес:")
    await query.answer()
```

Leave `build_profile_data` and `save_collected_profile` unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot_onboarding.py -q`
Expected: PASS (the surviving helper tests + the 5 new handler tests).

- [ ] **Step 5: Lint and import-check**

Run: `uv run ruff check src/quantuum/bot/handlers/onboarding.py tests/test_bot_onboarding.py`
Expected: `All checks passed!` (fix unused imports if flagged)
Run: `uv run python -c "import quantuum.bot.handlers.onboarding"`
Expected: no error.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/onboarding.py tests/test_bot_onboarding.py
git commit -m "feat(onboarding): birth place via Telegram location or geocoded text (confirm)"
```

---

### Task 5: Full suite + lint gate

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (existing tests minus the removed onboarding tests, plus the new geocoding/onboarding tests).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 3: Commit (only if ruff auto-fixed anything)**

```bash
git add -A && git commit -m "chore(geocoding): lint" || echo "nothing to commit"
```

---

## Manual verification (after merge, stack rebuilt)

The app images bake code at build time, so rebuild: `docker compose -f docker-compose.yml -f docker-compose.polling.yml up -d --build`. Then in a tenant bot, run onboarding:
1. At the birth-place step, send a **location** (📎 → Геопозиция, drop a pin) → it should save immediately and confirm "Готово!".
2. Re-run and instead **type a city** (e.g. "Bratsk") → it should reply "Нашёл: … — Верно?"; tap **Да** → saved. Tap **Другой адрес** → it re-asks.
3. `/blueprint` should generate using the derived coordinates/timezone.

## Out of scope

- Self-hosted Nominatim (later: set `geocoder_url`).
- Migrating existing `NatalProfile` rows.
- Multiple-result picker (top match + confirm only).
