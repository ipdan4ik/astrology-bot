from datetime import date, datetime, time, timezone
from decimal import Decimal

from quantuum.bot.ui import text

from .conftest import build_translator


def test_status_ru_mapping():
    assert text.STATUS_RU["done"] == "готов"
    assert text.STATUS_RU["failed"] == "ошибка"
    assert text.status_ru("unknown_status") == "unknown_status"  # fallback to raw


class _Profile:
    full_name = "Anna"
    birth_date = date(1980, 6, 24)
    birth_time = time(10, 0)
    birth_place = "Moscow"
    latitude = Decimal("55.7558")
    longitude = Decimal("37.6173")
    timezone = "Europe/Moscow"


async def test_render_profile_contains_fields_ru(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    rendered = await text.render_profile(i18n, _Profile())
    assert "👤 Твой профиль:" in rendered
    assert "Имя: Anna" in rendered
    assert "Дата рождения: 1980-06-24" in rendered
    assert "Время: 10:00" in rendered
    assert "Место: Moscow" in rendered
    assert "Координаты: 55.7558, 37.6173" in rendered
    assert "Таймзона: Europe/Moscow" in rendered


async def test_render_profile_uses_lang(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id, lang="en")
    rendered = await text.render_profile(i18n, _Profile())
    assert "👤 Your profile:" in rendered
    assert "Name: Anna" in rendered
    assert "Timezone: Europe/Moscow" in rendered


def test_render_history_label():
    class BP:
        id = 42
        status = "done"
        created_at = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    label = text.render_history_label(BP())
    assert "20.05" in label
    assert "готов" in label
