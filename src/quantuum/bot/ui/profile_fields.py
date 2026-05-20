from quantuum.bot.handlers.onboarding import (
    is_valid_timezone,
    parse_birth_date,
    parse_birth_time,
    parse_coords,
)

FIELD_PROMPTS = {
    "name": "Введи имя:",
    "birth_date": "Дата рождения ГГГГ-ММ-ДД (например 1980-06-24):",
    "birth_time": "Время рождения ЧЧ:ММ (например 10:00):",
    "birth_place": "Город рождения:",
    "coords": "Координаты «широта, долгота» (например 55.7558, 37.6173):",
    "timezone": "Таймзона IANA (например Europe/Moscow):",
}


def apply_field_edit(current: dict, field: str, raw: str) -> tuple[dict | None, str | None]:
    """Return (updated_profile_kwargs, None) on success, or (None, error) on
    invalid input. `current` holds the full upsert kwargs of the existing profile."""
    updated = dict(current)
    raw = raw.strip()
    if field == "name":
        if not raw:
            return None, "Имя не может быть пустым."
        updated["full_name"] = raw
    elif field == "birth_place":
        if not raw:
            return None, "Место не может быть пустым."
        updated["birth_place"] = raw
    elif field == "birth_date":
        parsed = parse_birth_date(raw)
        if parsed is None:
            return None, "Не понял дату. Формат ГГГГ-ММ-ДД."
        updated["birth_date"] = parsed
    elif field == "birth_time":
        parsed = parse_birth_time(raw)
        if parsed is None:
            return None, "Не понял время. Формат ЧЧ:ММ."
        updated["birth_time"] = parsed
    elif field == "coords":
        parsed = parse_coords(raw)
        if parsed is None:
            return None, "Не понял координаты. Формат «55.7558, 37.6173»."
        updated["latitude"], updated["longitude"] = parsed
    elif field == "timezone":
        if not is_valid_timezone(raw):
            return None, "Не понял таймзону. Например Europe/Moscow."
        updated["timezone"] = raw
    else:
        return None, "Неизвестное поле."
    return updated, None
