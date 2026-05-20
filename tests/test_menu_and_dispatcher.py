from aiogram.fsm.storage.redis import RedisStorage

from quantuum.bot.app import create_dispatcher
from quantuum.bot.ui import text


def test_create_dispatcher_uses_redis_storage_and_routers():
    dp = create_dispatcher()
    assert isinstance(dp.storage, RedisStorage)
    # menu router included last so its global text handlers are the fallback
    assert len(dp.sub_routers) >= 6


def test_menu_labels_are_routed():
    from quantuum.bot.handlers import menu

    assert menu.LABELS == {text.BTN_GENERATE, text.BTN_PROFILE, text.BTN_HISTORY, text.BTN_HELP}


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
