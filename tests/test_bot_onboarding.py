from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.onboarding import parse_coords, parse_birth_date, parse_birth_time


def test_parse_birth_date_valid():
    assert parse_birth_date("1980-06-24") == date(1980, 6, 24)


def test_parse_birth_date_invalid():
    assert parse_birth_date("nonsense") is None


def test_parse_birth_time_valid():
    assert parse_birth_time("10:00") == time(10, 0)


def test_parse_coords_valid():
    assert parse_coords("55.7558, 37.6173") == (Decimal("55.7558"), Decimal("37.6173"))


def test_parse_coords_invalid():
    assert parse_coords("abc") is None


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


def test_is_valid_timezone():
    from quantuum.bot.handlers.onboarding import is_valid_timezone

    assert is_valid_timezone("Europe/Moscow")
    assert is_valid_timezone("Asia/Irkutsk")
    assert not is_valid_timezone("/blueprint")
    assert not is_valid_timezone("Mars/Phobos")


def test_is_valid_timezone_rejects_directory_only_zone():
    # Regression: ZoneInfo("Europe") raises IsADirectoryError (an OSError), which the old
    # validator's (ZoneInfoNotFoundError, ValueError) tuple did not catch — so entering a
    # bare region crashed the timezone step instead of being rejected.
    from quantuum.bot.handlers.onboarding import is_valid_timezone

    assert not is_valid_timezone("Europe")
    assert not is_valid_timezone("America")
    assert not is_valid_timezone("Asia")


def test_is_valid_timezone_handles_blank_and_none():
    from quantuum.bot.handlers.onboarding import is_valid_timezone

    assert not is_valid_timezone("")
    assert not is_valid_timezone("   ")
    assert not is_valid_timezone(None)
    assert is_valid_timezone("  Europe/Moscow  ")  # surrounding whitespace tolerated


def test_parse_coords_rejects_out_of_range():
    assert parse_coords("91, 0") is None  # latitude > 90
    assert parse_coords("-91, 0") is None
    assert parse_coords("0, 181") is None  # longitude > 180
    assert parse_coords("0, -181") is None
    assert parse_coords("-90, -180") == (Decimal("-90"), Decimal("-180"))  # boundaries ok


def test_parsers_tolerate_none_text():
    # Non-text messages (stickers, photos, voice) arrive with message.text == None;
    # parsers must reject, not crash.
    assert parse_birth_date(None) is None
    assert parse_birth_time(None) is None
    assert parse_coords(None) is None


def test_parse_required_text():
    from quantuum.bot.handlers.onboarding import parse_required_text

    assert parse_required_text("  Anna  ") == "Anna"
    assert parse_required_text("") is None
    assert parse_required_text("   ") is None
    assert parse_required_text(None) is None


async def test_on_timezone_invalid_is_not_recorded(default_tenant, monkeypatch):
    """The user's example: an invalid timezone must NOT be saved. The handler rejects it,
    keeps the user on the timezone step, and never calls save_collected_profile."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    saved = AsyncMock()
    monkeypatch.setattr(ob, "save_collected_profile", saved)

    class _State:
        def __init__(self, data):
            self._data = dict(data)
            self.state = ob.Onboarding.timezone

        async def get_data(self):
            return dict(self._data)

        async def set_state(self, s):
            self.state = s

        async def clear(self):
            self.state = None

    state = _State(
        {
            "full_name": "Anna", "birth_date": "1980-06-24", "birth_time": "10:00",
            "birth_place": "Moscow", "latitude": "55.75", "longitude": "37.61",
        }
    )
    message = SimpleNamespace(text="Europe", answer=AsyncMock())
    account = SimpleNamespace(id=1, tenant_id=default_tenant.id)

    await ob.on_timezone(message, state, account=account)

    saved.assert_not_awaited()  # invalid tz never persisted
    assert state.state == ob.Onboarding.timezone  # still awaiting a valid tz
    message.answer.assert_awaited()
