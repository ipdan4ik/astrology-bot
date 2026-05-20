from aiogram import Bot
from arq.connections import RedisSettings

from quantuum.db.session import get_sessionmaker
from quantuum.logging_setup import configure_logging
from quantuum.settings import get_settings
from quantuum.tasks.blueprint import blueprint_generate


async def startup(ctx) -> None:
    configure_logging()
    ctx["sessionmaker"] = get_sessionmaker()
    ctx["bot"] = Bot(token=get_settings().bot_token)


async def shutdown(ctx) -> None:
    bot: Bot = ctx.get("bot")
    if bot is not None:
        await bot.session.close()


class WorkerSettings:
    functions = [blueprint_generate]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
