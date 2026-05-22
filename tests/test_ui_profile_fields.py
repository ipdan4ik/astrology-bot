from datetime import date, time

from quantuum.bot.ui.profile_fields import FIELD_PROMPT_KEYS, apply_field_edit


def _base():
    return {
        "full_name": "Anna",
        "birth_date": date(1980, 6, 24),
        "birth_time": time(10, 0),
    }


def test_prompt_keys_cover_text_fields_only():
    assert set(FIELD_PROMPT_KEYS) == {"name", "birth_date", "birth_time"}
    assert FIELD_PROMPT_KEYS["name"] == "profile.prompt.name"


def test_edit_birth_time_valid():
    updated, err_key = apply_field_edit(_base(), "birth_time", "07:45")
    assert err_key is None
    assert updated["birth_time"] == time(7, 45)


def test_edit_birth_time_invalid_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "birth_time", "nonsense")
    assert updated is None
    assert err_key == "profile.error.birth_time_invalid"



def test_removed_fields_return_unknown_field():
    # coords / timezone / birth_place are no longer handled here (place has its own flow).
    for field in ("coords", "timezone", "birth_place"):
        updated, err_key = apply_field_edit(_base(), field, "whatever")
        assert updated is None
        assert err_key == "profile.error.unknown_field"


def test_edit_name_passthrough():
    updated, err_key = apply_field_edit(_base(), "name", "  Anna B  ")
    assert err_key is None and updated["full_name"] == "Anna B"


def test_edit_name_empty_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "name", "   ")
    assert updated is None and err_key == "profile.error.name_empty"


def test_unknown_field_returns_error_key():
    updated, err_key = apply_field_edit(_base(), "bogus", "x")
    assert updated is None and err_key == "profile.error.unknown_field"
