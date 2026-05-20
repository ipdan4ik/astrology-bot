BTN_GENERATE = "🔮 Разбор"
BTN_PROFILE = "👤 Профиль"
BTN_HISTORY = "📜 История"
BTN_HELP = "ℹ️ Помощь"

STATUS_RU = {
    "pending": "в очереди",
    "calculating": "считаю",
    "generating": "генерирую",
    "done": "готов",
    "failed": "ошибка",
    "refunded": "возврат",
}

HELP_TEXT = (
    "Я строю персональный астрологический разбор (Quantuum Blueprint) по твоим "
    "натальным данным.\n\n"
    "Меню снизу:\n"
    f"{BTN_GENERATE} — сгенерировать разбор\n"
    f"{BTN_PROFILE} — посмотреть и изменить натальные данные\n"
    f"{BTN_HISTORY} — прошлые генерации\n\n"
    "Команды: /start /profile /blueprint\n"
    "Поддержка: @quantuum_support"
)


def status_ru(status: str) -> str:
    return STATUS_RU.get(status, status)


def render_profile(profile) -> str:
    return (
        "👤 Твой профиль:\n\n"
        f"Имя: {profile.full_name}\n"
        f"Дата рождения: {profile.birth_date.isoformat()}\n"
        f"Время: {profile.birth_time.strftime('%H:%M')}\n"
        f"Место: {profile.birth_place}\n"
        f"Координаты: {profile.latitude}, {profile.longitude}\n"
        f"Таймзона: {profile.timezone}"
    )


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
