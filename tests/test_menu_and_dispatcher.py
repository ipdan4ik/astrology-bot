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
