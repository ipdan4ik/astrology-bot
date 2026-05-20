from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from quantuum.bot.middleware.account import AccountMiddleware
from quantuum.settings import get_settings


def create_bot() -> Bot:
    return Bot(token=get_settings().bot_token)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=RedisStorage.from_url(get_settings().redis_url))
    from quantuum.bot.middleware.tenant import TenantMiddleware

    dp.message.middleware(TenantMiddleware())
    dp.message.middleware(AccountMiddleware())
    dp.callback_query.middleware(TenantMiddleware())
    dp.callback_query.middleware(AccountMiddleware())
    from quantuum.bot.handlers import generate, history, menu, onboarding, profile, start

    dp.include_router(start.router)
    dp.include_router(generate.router)
    dp.include_router(profile.router)
    dp.include_router(history.router)
    dp.include_router(onboarding.router)
    dp.include_router(menu.router)
    return dp
