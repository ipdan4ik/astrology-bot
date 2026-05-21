from datetime import date, time
from decimal import Decimal

from quantuum.bot.ui.profile_fields import FIELD_PROMPT_KEYS, apply_field_edit


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


def test_prompt_keys_cover_all_fields():
    assert set(FIELD_PROMPT_KEYS) == {
        "name", "birth_date", "birth_time", "birth_place", "coords", "timezone"
    }
    # Each value is an i18n key, not a literal RU string.
    assert FIELD_PROMPT_KEYS["name"] == "profile.prompt.name"
    assert FIELD_PROMPT_KEYS["birth_date"] == "profile.prompt.birth_date"


def test_edit_birth_time_valid():
    updated, err_key = apply_field_edit(_base(), "birth_time", "07:45")
    assert err_key is None
    assert updated["birth_time"] == time(7, 45)


def test_edit_birth_time_invalid_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "birth_time", "nonsense")
    assert updated is None
    assert err_key == "profile.error.birth_time_invalid"


def test_edit_coords_updates_both():
    updated, err_key = apply_field_edit(_base(), "coords", "10.0, 20.0")
    assert err_key is None
    assert updated["latitude"] == Decimal("10.0")
    assert updated["longitude"] == Decimal("20.0")


def test_edit_timezone_invalid_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "timezone", "/blueprint")
    assert updated is None
    assert err_key == "profile.error.timezone_invalid"


def test_edit_name_passthrough():
    updated, err_key = apply_field_edit(_base(), "name", "  Anna B  ")
    assert err_key is None and updated["full_name"] == "Anna B"


def test_edit_name_empty_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "name", "   ")
    assert updated is None and err_key == "profile.error.name_empty"


def test_unknown_field_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "bogus", "x")
    assert updated is None and err_key == "profile.error.unknown_field"
