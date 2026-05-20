from datetime import date, time
from decimal import Decimal

from quantuum.bot.ui.profile_fields import FIELD_PROMPTS, apply_field_edit


def _base():
    return {
        "full_name": "Anna",
        "birth_date": date(1980, 6, 24),
        "birth_time": time(10, 0),
        "birth_place": "Moscow",
        "latitude": Decimal("55.7558"),
        "longitude": Decimal("37.6173"),
        "timezone": "Europe/Moscow",
    }


def test_prompts_cover_all_fields():
    assert set(FIELD_PROMPTS) == {"name", "birth_date", "birth_time", "birth_place", "coords", "timezone"}


def test_edit_birth_time_valid():
    updated, err = apply_field_edit(_base(), "birth_time", "07:45")
    assert err is None
    assert updated["birth_time"] == time(7, 45)


def test_edit_birth_time_invalid():
    updated, err = apply_field_edit(_base(), "birth_time", "nonsense")
    assert updated is None
    assert err is not None


def test_edit_coords_updates_both():
    updated, err = apply_field_edit(_base(), "coords", "10.0, 20.0")
    assert err is None
    assert updated["latitude"] == Decimal("10.0")
    assert updated["longitude"] == Decimal("20.0")


def test_edit_timezone_invalid():
    updated, err = apply_field_edit(_base(), "timezone", "/blueprint")
    assert updated is None and err is not None


def test_edit_name_passthrough():
    updated, err = apply_field_edit(_base(), "name", "  Anna B  ")
    assert err is None and updated["full_name"] == "Anna B"
