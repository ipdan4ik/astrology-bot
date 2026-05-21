from quantuum.bot.handlers.buy import build_buy_menu
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.bootstrap import ensure_global_plans


async def test_build_buy_menu_lists_active_plans(session, default_tenant):
    await ensure_global_plans(session)
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id)

    assert "★" in text  # Star pricing shown
    callbacks = [
        BuyCb.unpack(btn.callback_data)
        for row in kb.inline_keyboard
        for btn in row
    ]
    kinds = {(c.kind) for c in callbacks}
    assert "subscription" in kinds
    assert "package" in kinds
    assert all(c.action == "pick" for c in callbacks)


async def test_build_buy_menu_empty_when_no_plans(session, default_tenant):
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id)
    assert kb.inline_keyboard == []
