from datetime import date, datetime, time, timezone
from decimal import Decimal

from quantuum.bot.ui import text


def test_menu_labels_present():
    assert text.BTN_GENERATE and text.BTN_PROFILE and text.BTN_HISTORY and text.BTN_HELP


def test_status_ru_mapping():
    assert text.STATUS_RU["done"] == "готов"
    assert text.STATUS_RU["failed"] == "ошибка"
    assert text.status_ru("unknown_status") == "unknown_status"  # fallback to raw


def test_render_profile_contains_fields():
    class P:
        full_name = "Anna"
        birth_date = date(1980, 6, 24)
        birth_time = time(10, 0)
        birth_place = "Moscow"
        latitude = Decimal("55.7558")
        longitude = Decimal("37.6173")
        timezone = "Europe/Moscow"
    rendered = text.render_profile(P())
    assert "Anna" in rendered
    assert "1980-06-24" in rendered
    assert "Europe/Moscow" in rendered


def test_render_history_label():
    class BP:
        id = 42
        status = "done"
        created_at = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    label = text.render_history_label(BP())
    assert "20.05" in label
    assert "готов" in label
