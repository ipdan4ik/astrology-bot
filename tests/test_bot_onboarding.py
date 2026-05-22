from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.onboarding import parse_birth_date, parse_birth_time


def test_parse_birth_date_valid():
    assert parse_birth_date("1980-06-24") == date(1980, 6, 24)


def test_parse_birth_date_invalid():
    assert parse_birth_date("nonsense") is None


def test_parse_birth_time_valid():
    assert parse_birth_time("10:00") == time(10, 0)


async def test_finish_onboarding_saves_profile(session, default_tenant):
    from quantuum.bot.handlers.onboarding import save_collected_profile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="3")
    profile = await save_collected_profile(
        session,
        account=acc,
        data={
            "full_name": "Anna",
            "birth_date": date(1980, 6, 24),
            "birth_time": time(10, 0),
            "birth_place": "Moscow",
            "latitude": Decimal("55.7558"),
            "longitude": Decimal("37.6173"),
            "timezone": "Europe/Moscow",
        },
    )
    assert profile.id is not None
    assert profile.full_name == "Anna"


def test_build_profile_data_roundtrips_isoformat_time():
    # on_birth_time stores time as isoformat ("HH:MM:SS"); reconstruction must
    # not drop it to None (regression: parse_birth_time only accepted "HH:MM").
    from quantuum.bot.handlers.onboarding import build_profile_data

    raw = {
        "full_name": "Даниил",
        "birth_date": "2001-03-04",
        "birth_time": "10:30:00",
        "birth_place": "Bratsk",
        "latitude": "55.7558",
        "longitude": "37.6173",
    }
    data = build_profile_data(raw, "Europe/Moscow")
    assert data["birth_time"] == time(10, 30)
    assert data["birth_date"] == date(2001, 3, 4)
    assert data["latitude"] == Decimal("55.7558")
    assert data["timezone"] == "Europe/Moscow"


def test_parsers_tolerate_none_text():
    # Non-text messages (stickers, photos, voice) arrive with message.text == None;
    # parsers must reject, not crash.
    assert parse_birth_date(None) is None
    assert parse_birth_time(None) is None


def test_parse_required_text():
    from quantuum.bot.handlers.onboarding import parse_required_text

    assert parse_required_text("  Anna  ") == "Anna"
    assert parse_required_text("") is None
    assert parse_required_text("   ") is None
    assert parse_required_text(None) is None


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
