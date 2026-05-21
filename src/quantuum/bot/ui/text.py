from quantuum.i18n import Translator
from quantuum.i18n.seed_strings import BASE_STRINGS

STATUS_RU = {
    "pending": "в очереди",
    "calculating": "считаю",
    "generating": "генерирую",
    "done": "готов",
    "failed": "ошибка",
    "refunded": "возврат",
}

# Reply-menu button keys, in display order. Routing matches the rendered label
# in any enabled language, so callers derive label sets from BASE_STRINGS.
MENU_BUTTON_KEYS = ("btn.generate", "btn.profile", "btn.history", "btn.help")


def menu_button_labels(key: str) -> set[str]:
    """Return every localised label for a menu button key (across all seeded langs).

    Used for message routing so a button pressed in any enabled language matches.
    """
    return set(BASE_STRINGS[key].values())


def all_menu_labels() -> set[str]:
    """All localised labels for every reply-menu button (across all seeded langs)."""
    labels: set[str] = set()
    for key in MENU_BUTTON_KEYS:
        labels |= menu_button_labels(key)
    return labels


def status_ru(status: str) -> str:
    return STATUS_RU.get(status, status)


async def render_profile(i18n: Translator, profile) -> str:
    lines = [
        await i18n("profile.title"),
        "",
        await i18n("profile.name", name=profile.full_name),
        await i18n("profile.birth_date", birth_date=profile.birth_date.isoformat()),
        await i18n("profile.birth_time", birth_time=profile.birth_time.strftime("%H:%M")),
        await i18n("profile.place", place=profile.birth_place),
        await i18n("profile.coords", lat=profile.latitude, lon=profile.longitude),
        await i18n("profile.timezone", timezone=profile.timezone),
    ]
    return "\n".join(lines)


def render_history_label(bp) -> str:
    return f"🔮 {bp.created_at.strftime('%d.%m')} · {status_ru(bp.status)}"


def render_detail(bp) -> str:
    lines = [
        f"🔮 Разбор #{bp.id}",
        f"Статус: {status_ru(bp.status)}",
        f"Создан: {bp.created_at.strftime('%d.%m.%Y %H:%M')}",
    ]
    if bp.completed_at:
        lines.append(f"Готов: {bp.completed_at.strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(lines)
