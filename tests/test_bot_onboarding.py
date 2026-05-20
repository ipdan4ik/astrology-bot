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
