from datetime import date, datetime, time, timezone
from decimal import Decimal

from quantuum.bot.ui import text

from .conftest import build_translator


class _Profile:
    full_name = "Anna"
    birth_date = date(1980, 6, 24)
    birth_time = time(10, 0)
    birth_place = "Moscow"
    latitude = Decimal("55.7558")
    longitude = Decimal("37.6173")
    timezone = "Europe/Moscow"


async def test_status_label_resolves_seeded_word(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    assert await text.status_label(i18n, "done") == "готов"
    assert await text.status_label(i18n, "failed") == "ошибка"


async def test_status_label_uses_lang(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id, lang="en")
    assert await text.status_label(i18n, "done") == "done"
    assert await text.status_label(i18n, "pending") == "queued"


async def test_render_profile_contains_fields_ru(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    rendered = await text.render_profile(i18n, _Profile())
    assert "👤 Твой профиль:" in rendered
    assert "Имя: Anna" in rendered
    assert "Дата рождения: 1980-06-24" in rendered
    assert "Время: 10:00" in rendered
    assert "Место: Moscow" in rendered
    # Coordinates and timezone are no longer shown.
    assert "55.7558" not in rendered
    assert "Europe/Moscow" not in rendered


async def test_render_profile_uses_lang(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id, lang="en")
    rendered = await text.render_profile(i18n, _Profile())
    assert "👤 Your profile:" in rendered
    assert "Name: Anna" in rendered
    assert "Europe/Moscow" not in rendered  # timezone hidden


async def test_render_history_label(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)

    class BP:
        id = 42
        status = "done"
        created_at = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)

    label = await text.render_history_label(i18n, BP())
    assert "20.05" in label
    assert "готов" in label


async def test_render_detail_localised(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)

    class BP:
        id = 7
        status = "done"
        created_at = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
        completed_at = datetime(2026, 5, 20, 9, 5, tzinfo=timezone.utc)

    detail = await text.render_detail(i18n, BP())
    assert "🔮 Blueprint #7" in detail
    assert "Статус: готов" in detail
    assert "Создан: 20.05.2026 09:00" in detail
    assert "Готов: 20.05.2026 09:05" in detail
