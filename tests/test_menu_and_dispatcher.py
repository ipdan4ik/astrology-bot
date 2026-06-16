from aiogram.fsm.storage.redis import RedisStorage

from quantuum.bot.app import create_dispatcher
from quantuum.bot.ui import text


def test_create_dispatcher_uses_redis_storage_and_routers():
    dp = create_dispatcher()
    assert isinstance(dp.storage, RedisStorage)
    # menu router included last so its global text handlers are the fallback
    assert len(dp.sub_routers) >= 6


def test_menu_button_labels_cover_all_langs():
    # Routing must match a button pressed in any enabled language, so the
    # label sets are derived from BASE_STRINGS (ru + en), not a single literal.
    assert text.menu_button_labels("btn.ask") >= {"❓ Спросить астролога", "❓ Ask the astrologer"}
    assert text.menu_button_labels("btn.profile") >= {"👤 Профиль", "👤 Profile"}
    assert text.menu_button_labels("btn.history") >= {"📜 История", "📜 History"}
    assert text.menu_button_labels("btn.help") >= {"ℹ️ Помощь", "ℹ️ Help"}


def test_menu_labels_routed_include_both_langs():
    from quantuum.bot.handlers import menu

    assert "📖 Разборы" in menu.LABELS and "📖 Readings" in menu.LABELS
    assert "👤 Профиль" in menu.LABELS and "👤 Profile" in menu.LABELS


def test_blueprint_button_is_routed_from_main_menu():
    from quantuum.bot.handlers import menu

    # The Blueprint button is now a top-level main-menu button (label is the same
    # in ru/en), so its label must be in the routed set.
    assert "🔮 Blueprint" in menu.LABELS
    assert "🔮 Blueprint" in menu._GENERATE_LABELS


async def test_on_generate_btn_dispatches_to_run_generate(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from quantuum.bot.handlers import menu

    spy = AsyncMock()
    monkeypatch.setattr(menu, "run_generate", spy)

    message = MagicMock()
    account = object()
    i18n = object()
    await menu.on_generate_btn(message, account=account, chat_id=42, i18n=i18n)

    spy.assert_awaited_once_with(message, account, 42, i18n)


def test_tenant_middleware_registered_before_account():
    import sys

    # Reload handler modules so their module-level routers are fresh
    # (allows create_dispatcher() to be called again after the first test)
    for mod_name in list(sys.modules):
        if mod_name.startswith("quantuum.bot.handlers") or mod_name == "quantuum.bot.app":
            del sys.modules[mod_name]

    from quantuum.bot.app import create_dispatcher
    from quantuum.bot.middleware.account import AccountMiddleware
    from quantuum.bot.middleware.tenant import TenantMiddleware

    dp = create_dispatcher()
    msg_mw = list(dp.message.middleware)
    types = [type(m) for m in msg_mw]
    assert TenantMiddleware in types
    assert AccountMiddleware in types
    assert types.index(TenantMiddleware) < types.index(AccountMiddleware)
