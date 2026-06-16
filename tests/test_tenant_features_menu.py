import pytest

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.keyboards import main_menu_kb, readings_menu_kb
from quantuum.domain.tenant_features import set_feature_enabled


async def _disable(session, tenant_id, *keys, by_account_id):
    for k in keys:
        await set_feature_enabled(
            session,
            tenant_id=tenant_id,
            key=k,
            enabled=False,
            by_account_id=by_account_id,
        )
    await session.commit()


def _button_texts(kb) -> list[str]:
    return [btn.text for row in kb.keyboard for btn in row]


def _inline_button_texts(kb) -> list[str]:
    return [btn.text for row in kb.inline_keyboard for btn in row]


async def test_main_menu_full_when_all_enabled(session, default_tenant, build_translator):
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = " ".join(_button_texts(kb))
    # Top-level surface buttons all present.
    assert "Blueprint" in texts  # blueprint is its own top-level button
    assert "Разборы" in texts  # readings hub (contains transits + specialty)
    assert "Спросить" in texts or "Вопрос" in texts  # qa
    assert "Ежедневн" in texts
    # Always-on
    assert "Профиль" in texts


async def test_main_menu_hides_blueprint_button_when_disabled(
    session, default_tenant, build_translator
):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_no_blueprint"
    )
    await _disable(session, default_tenant.id, "blueprint", by_account_id=acc.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = " ".join(_button_texts(kb))
    assert "Blueprint" not in texts
    # The readings hub stays (transits + specialty kinds still enabled).
    assert "Разборы" in texts


async def test_main_menu_hides_disabled_surfaces(session, default_tenant, build_translator):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_menu"
    )
    await _disable(session, default_tenant.id, "qa", "daily", by_account_id=acc.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = " ".join(_button_texts(kb))
    # qa label patterns absent (whichever variant the project uses for btn.ask)
    assert "Спросить" not in texts and "Вопрос-ответ" not in texts
    # daily label absent
    assert "Ежедневн" not in texts


async def test_main_menu_hides_readings_button_when_all_readings_off(
    session, default_tenant, build_translator
):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_no_readings"
    )
    await _disable(
        session,
        default_tenant.id,
        "blueprint", "transits",
        "reading.bazi", "reading.numerology", "reading.human_design",
        "reading.astrology", "reading.vedic", "reading.gene_keys",
        "reading.mayan", "reading.aspects",
        "reading.tarot", "reading.iching",
        by_account_id=acc.id,
    )
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    # The btn.readings label in RU (look it up in seed_strings before assuming) should be absent.
    # Test by checking that the labels of other buttons are still present (sanity)
    # and that the readings label is NOT in the kb.
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = _button_texts(kb)
    # Sanity: history button still present.
    assert any("История" in t or "📜" in t for t in texts)
    # Readings hub button must be absent when all reading kinds are disabled.
    readings_hub_label = "📖 Разборы"  # BASE_STRINGS["btn.readings"]["ru"]
    assert readings_hub_label not in texts, f"Readings hub button should be hidden, got {texts}"


async def test_readings_menu_full_when_all_enabled(session, default_tenant, build_translator):
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await readings_menu_kb(i18n, default_tenant.id)
    texts = _inline_button_texts(kb)
    assert len(texts) == 11  # transits + 10 reading kinds (blueprint is a main-menu button)


async def test_readings_menu_hides_disabled_kinds(session, default_tenant, build_translator):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_partial"
    )
    await _disable(
        session, default_tenant.id,
        "reading.bazi", "reading.vedic",
        by_account_id=acc.id,
    )
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await readings_menu_kb(i18n, default_tenant.id)
    texts = _inline_button_texts(kb)
    assert len(texts) == 9  # transits + 8 remaining kinds (blueprint is a main-menu button)


@pytest.fixture
def build_translator():
    from tests.conftest import build_translator as bt
    return bt
