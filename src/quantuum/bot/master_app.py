from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from quantuum.bot.middleware.account import AccountMiddleware
from quantuum.bot.middleware.tenant import TenantMiddleware
from quantuum.settings import get_settings


def create_master_dispatcher() -> Dispatcher:
    """Dispatcher for the platform master/onboarding bot — onboarding handlers only."""
    dp = Dispatcher(storage=RedisStorage.from_url(get_settings().redis_url))
    dp.message.middleware(TenantMiddleware())
    dp.message.middleware(AccountMiddleware())
    dp.callback_query.middleware(TenantMiddleware())
    dp.callback_query.middleware(AccountMiddleware())
    from quantuum.bot.handlers import master_onboarding

    dp.include_router(master_onboarding.router)
    return dp
