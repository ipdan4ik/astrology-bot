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
