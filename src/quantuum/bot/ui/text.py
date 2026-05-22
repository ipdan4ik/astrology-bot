from quantuum.i18n import Translator
from quantuum.i18n.seed_strings import BASE_STRINGS

# Reply-menu button keys, in display order. Routing matches the rendered label
# in any enabled language, so callers derive label sets from BASE_STRINGS.
MENU_BUTTON_KEYS = ("btn.generate", "btn.ask", "btn.transits", "btn.daily", "btn.profile", "btn.history", "btn.help")


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


async def status_label(i18n: Translator, status: str) -> str:
    """Localised word for a blueprint *status* (falls back to the raw value)."""
    return await i18n(f"status.{status}", default=status)


async def render_profile(i18n: Translator, profile) -> str:
    lines = [
        await i18n("profile.title"),
        "",
        await i18n("profile.name", name=profile.full_name),
        await i18n("profile.birth_date", birth_date=profile.birth_date.isoformat()),
        await i18n("profile.birth_time", birth_time=profile.birth_time.strftime("%H:%M")),
        await i18n("profile.place", place=profile.birth_place),
    ]
    return "\n".join(lines)


async def render_history_label(i18n: Translator, bp) -> str:
    return await i18n(
        "history.label",
        date=bp.created_at.strftime("%d.%m"),
        status=await status_label(i18n, bp.status),
    )


async def render_detail(i18n: Translator, bp) -> str:
    lines = [
        await i18n("history.detail_header", id=bp.id),
        await i18n("history.detail_status", status=await status_label(i18n, bp.status)),
        await i18n("history.detail_created", created_at=bp.created_at.strftime("%d.%m.%Y %H:%M")),
    ]
    if bp.completed_at:
        lines.append(
            await i18n(
                "history.detail_ready", completed_at=bp.completed_at.strftime("%d.%m.%Y %H:%M")
            )
        )
    return "\n".join(lines)
