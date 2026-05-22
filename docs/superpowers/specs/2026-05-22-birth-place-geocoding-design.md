# Birth-Place Geocoding — Design Spec

**Date:** 2026-05-22
**Status:** Approved (ready for implementation plan)
**Branch:** feat/birth-place-geocoding

## Goal

Stop asking the user to type coordinates and an IANA timezone during onboarding. Instead, the
birth-place step accepts **either** a Telegram location **or** typed text (city / part of an
address); the backend derives latitude, longitude, and timezone automatically.

## Background — current onboarding

`src/quantuum/bot/handlers/onboarding.py` runs an FSM:
`full_name → birth_date → birth_time → birth_place → coords → timezone → save`.
The `coords` step parses a "lat, lon" string (`parse_coords`) and the `timezone` step validates
an IANA name (`is_valid_timezone`); `on_timezone` then saves the profile via
`save_collected_profile` (which calls `upsert_natal_profile`). `build_profile_data(raw, timezone)`
reconstructs typed values (dates/times via `fromisoformat`, `Decimal` for lat/lon) from the
FSM's string-only storage.

`NatalProfile` already has `latitude: Decimal`, `longitude: Decimal`, `timezone: str`,
`birth_place: str` — no schema change is needed; we just populate them from geocoding.

The `account` middleware (`src/quantuum/bot/middleware/account.py`) injects `account: Account`
into both message and callback handlers (confirmed: `buy.py`/`daily.py` callbacks receive it),
so the typed-path confirm callback can take `account`.

`httpx>=0.28` is already a direct dependency. `OnboardCb(CallbackData, prefix="onb")` has an
`action: str` field.

## New onboarding flow

FSM: `full_name → birth_date → birth_time → birth_place → birth_place_confirm → save`.
The `coords` and `timezone` states are removed.

**birth_place prompt (ru):**
"Место рождения: пришли геопозицию (📎 → Геопозиция, можно поставить точку на карте) или напиши
город / часть адреса."

**Location path** (`@router.message(Onboarding.birth_place, F.location)`):
- `lat, lon = message.location.latitude, message.location.longitude` (exact).
- `tz = coords_to_timezone(lat, lon)`.
- `display_name = (await reverse(lat, lon)) or f"📍 {lat:.4f}, {lon:.4f}"` (best-effort; reverse
  failure falls back to the coord string).
- Save directly (it's exact — **no confirm**): store the resolved values in FSM, then
  `build_profile_data` + `save_collected_profile`, clear state, reply "Готово! Профиль сохранён.
  Команда /blueprint сгенерирует твой разбор."

**Text path** (`@router.message(Onboarding.birth_place, F.text)`):
- `results = await geocode(text)`.
- Empty → re-prompt, stay in `birth_place`: "Не нашёл это место. Уточни город/адрес или пришли
  геопозицию."
- Otherwise take `results[0]` (Nominatim orders by importance). Compute
  `tz = coords_to_timezone(lat, lon)`. Store pending values in FSM
  (`birth_place=display_name, latitude=str(lat), longitude=str(lon), timezone=tz`), set state
  `birth_place_confirm`, and **confirm**: "Нашёл: {display_name}\nЧасовой пояс: {tz}\n\nВерно?"
  with an inline keyboard: **Да** (`OnboardCb(action="geo_confirm")`) / **Другой адрес**
  (`OnboardCb(action="geo_retry")`).

**Confirm callback** (`@router.callback_query(OnboardCb.filter(F.action == "geo_confirm"), Onboarding.birth_place_confirm)`):
- Read pending values from FSM, `build_profile_data` + `save_collected_profile(account=account)`,
  clear state, reply "Готово!". Takes `account: Account`.

**Retry callback** (`@router.callback_query(OnboardCb.filter(F.action == "geo_retry"))`):
- Set state back to `Onboarding.birth_place`, reply "Пришли геопозицию или другой город/адрес:".

A non-text, non-location message in `birth_place` (e.g. a sticker) falls through to a catch
handler that re-prompts (or is naturally not matched and ignored — keep the existing
plain-prompt behavior by adding a fallback `@router.message(Onboarding.birth_place)` that
re-prompts).

## New module: `src/quantuum/geocoding.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class GeoResult:
    lat: float
    lon: float
    display_name: str


async def geocode(query: str, *, limit: int = 1) -> list[GeoResult]:
    """Forward-geocode a free-text place via a Nominatim-compatible endpoint.

    GET {settings.geocoder_url}/search?q=...&format=jsonv2&limit=...&accept-language=ru
    with a required User-Agent header. Network/HTTP errors are caught and logged; returns []
    so the caller can re-prompt. Trims the query; empty query returns [].
    """


async def reverse(lat: float, lon: float) -> GeoResult | None:
    """Reverse-geocode coordinates to a display name (best-effort; None on failure).

    GET {settings.geocoder_url}/reverse?lat=...&lon=...&format=jsonv2&accept-language=ru
    """


def coords_to_timezone(lat: float, lon: float) -> str:
    """IANA timezone for coordinates via timezonefinder (offline, deterministic).

    Uses a module-level TimezoneFinder singleton. Falls back to closest_timezone_at when
    timezone_at returns None (e.g. coastal/edge coordinates). Returns "UTC" only if even the
    closest lookup yields nothing (effectively never for land coordinates).
    """
```

- HTTP via `httpx.AsyncClient` with a timeout (e.g. 10s) and the configured `User-Agent`.
- `TimezoneFinder` is instantiated once at module load (loads its data once).
- Nominatim usage: a single request per onboarding step, well under the public server's ~1 req/s.

## Settings — `src/quantuum/settings.py`

```python
    geocoder_url: str = "https://nominatim.openstreetmap.org"
    geocoder_user_agent: str = "quantuum-bot (onboarding geocoder)"
```

(Configurable so production can later point at a self-hosted Nominatim with no code change.)

## Dependencies

Add `timezonefinder` (bundles ~50 MB of timezone polygon data; may pull `numpy`/`cffi` via its
resolver — accept whatever `uv` locks). `httpx` is already present.

## Removed code

- FSM states `Onboarding.coords`, `Onboarding.timezone`; handlers `on_coords`, `on_timezone`.
- Helpers `parse_coords`, `is_valid_timezone` (now unused; both their steps are gone).
- Their tests in `tests/test_bot_onboarding.py`
  (`test_parse_coords_*`, `test_is_valid_timezone_*`, `test_on_timezone_invalid_is_not_recorded`).
  The `full_name` / `birth_date` / `birth_time` validation and tests stay.

## Error handling

- `geocode` network/timeout/non-200 → log + return `[]` → user re-prompted (stays in birth_place).
- `reverse` failure (location path) → fall back to a `📍 lat, lon` display name; never blocks the save.
- `coords_to_timezone` `None` from `timezone_at` → `closest_timezone_at`; only "UTC" as a last resort.
- Sticker/photo/etc. in birth_place → fallback handler re-prompts.

## Testing

- `geocoding.py`:
  - `geocode` parses a mocked Nominatim JSON payload into `GeoResult`s; empty response → `[]`;
    an HTTP error (mock raising) → `[]`. Mock the `httpx.AsyncClient` call (no real network).
  - `coords_to_timezone` with real (offline) timezonefinder: `(55.7558, 37.6173)` → `"Europe/Moscow"`,
    `(52.52, 13.405)` → `"Europe/Berlin"`.
- Onboarding handlers (reuse the `_FakeState` pattern; monkeypatch `geocode`/`reverse`/`coords_to_timezone`
  and `save_collected_profile`/`get_sessionmaker` as the existing tests do):
  - **location path**: a `message` with `.location` → `save_collected_profile` awaited with the
    derived lat/lon/tz; state cleared.
  - **text happy path**: text → mocked `geocode` returns one result → confirm prompt shown, state
    `birth_place_confirm`; then `geo_confirm` callback → `save_collected_profile` awaited; state cleared.
  - **text not found**: mocked `geocode` returns `[]` → re-prompt, no save, state stays `birth_place`.
  - **retry**: `geo_retry` callback → state back to `birth_place`.
- No test makes a real Nominatim request.

## Files

| File | Change |
|------|--------|
| `src/quantuum/geocoding.py` | **new** — `GeoResult`, `geocode`, `reverse`, `coords_to_timezone` |
| `src/quantuum/settings.py` | add `geocoder_url`, `geocoder_user_agent` |
| `src/quantuum/bot/handlers/onboarding.py` | new birth_place flow (location/text + confirm); remove coords/timezone states, handlers, `parse_coords`, `is_valid_timezone` |
| `src/quantuum/bot/ui/callbacks.py` | document `geo_confirm`/`geo_retry` actions on `OnboardCb` (no structural change needed) |
| `pyproject.toml` | add `timezonefinder` |
| `tests/test_geocoding.py` | **new** — geocode parsing + coords_to_timezone |
| `tests/test_bot_onboarding.py` | replace coords/timezone tests with location/text/confirm handler tests |

## Out of scope

- Self-hosted Nominatim (a later config swap via `geocoder_url`).
- Migrating existing `NatalProfile` rows.
- City autocomplete / multiple-result picker (top match + confirm is enough).
