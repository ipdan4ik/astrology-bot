from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.bot.middleware.account import AccountMiddleware
from quantuum.settings import get_settings


def create_bot() -> Bot:
    return Bot(token=get_settings().bot_token)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccountMiddleware())
    from quantuum.bot.handlers import generate, onboarding, start

    dp.include_router(start.router)
    dp.include_router(onboarding.router)
    dp.include_router(generate.router)
    return dp
