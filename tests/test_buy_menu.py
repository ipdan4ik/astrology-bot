from quantuum.bot.handlers.buy import build_buy_menu
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.bootstrap import ensure_global_plans

from .conftest import build_translator


async def test_build_buy_menu_lists_active_plans(session, default_tenant):
    await ensure_global_plans(session)
    i18n = await build_translator(session, default_tenant.id)
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id, i18n=i18n)

    assert text == "Выбери, что купить (оплата звёздами Telegram ★):"
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("★" in label for label in labels)  # Star pricing shown
    assert any("разборов" in label for label in labels)  # localised package line
    callbacks = [
        BuyCb.unpack(btn.callback_data)
        for row in kb.inline_keyboard
        for btn in row
    ]
    kinds = {(c.kind) for c in callbacks}
    assert "subscription" in kinds
    assert "package" in kinds
    assert all(c.action == "pick" for c in callbacks)


async def test_build_buy_menu_localised_en(session, default_tenant):
    await ensure_global_plans(session)
    i18n = await build_translator(session, default_tenant.id, lang="en")
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id, i18n=i18n)

    assert text == "Choose what to buy (payment via Telegram Stars ★):"
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("readings" in label for label in labels)


async def test_build_buy_menu_empty_when_no_plans(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id, i18n=i18n)
    assert kb.inline_keyboard == []
