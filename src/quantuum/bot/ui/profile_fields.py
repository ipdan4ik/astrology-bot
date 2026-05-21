from quantuum.bot.handlers.onboarding import (
    is_valid_timezone,
    parse_birth_date,
    parse_birth_time,
    parse_coords,
)

# field name -> i18n prompt key (resolved by the handler via the Translator).
FIELD_PROMPT_KEYS = {
    "name": "profile.prompt.name",
    "birth_date": "profile.prompt.birth_date",
    "birth_time": "profile.prompt.birth_time",
    "birth_place": "profile.prompt.birth_place",
    "coords": "profile.prompt.coords",
    "timezone": "profile.prompt.timezone",
}


def apply_field_edit(current: dict, field: str, raw: str) -> tuple[dict | None, str | None]:
    """Return (updated_profile_kwargs, None) on success, or (None, error_key) on
    invalid input. `current` holds the full upsert kwargs of the existing profile.

    The error component is an i18n key (e.g. ``profile.error.birth_time_invalid``);
    the handler resolves it to a localised message via the Translator.
    """
    updated = dict(current)
    raw = raw.strip()
    if field == "name":
        if not raw:
            return None, "profile.error.name_empty"
        updated["full_name"] = raw
    elif field == "birth_place":
        if not raw:
            return None, "profile.error.place_empty"
        updated["birth_place"] = raw
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
    elif field == "coords":
        parsed = parse_coords(raw)
        if parsed is None:
            return None, "profile.error.coords_invalid"
        updated["latitude"], updated["longitude"] = parsed
    elif field == "timezone":
        if not is_valid_timezone(raw):
            return None, "profile.error.timezone_invalid"
        updated["timezone"] = raw
    else:
        return None, "profile.error.unknown_field"
    return updated, None
