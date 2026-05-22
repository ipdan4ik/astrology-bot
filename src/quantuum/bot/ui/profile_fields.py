from quantuum.bot.handlers.onboarding import parse_birth_date, parse_birth_time

# field name -> i18n prompt key (resolved by the handler via the Translator).
# birth_place is handled by its own geocoding sub-flow, not via apply_field_edit.
FIELD_PROMPT_KEYS = {
    "name": "profile.prompt.name",
    "birth_date": "profile.prompt.birth_date",
    "birth_time": "profile.prompt.birth_time",
}


def apply_field_edit(current: dict, field: str, raw: str) -> tuple[dict | None, str | None]:
    """Return (updated_profile_kwargs, None) on success, or (None, error_key) on
    invalid input. `current` holds the full upsert kwargs of the existing profile.

    Only the free-text fields are handled here; birth place (with derived coordinates
    and timezone) goes through the geocoding sub-flow in the profile handler.
    """
    updated = dict(current)
    raw = raw.strip()
    if field == "name":
        if not raw:
            return None, "profile.error.name_empty"
        updated["full_name"] = raw
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
    else:
        return None, "profile.error.unknown_field"
    return updated, None
