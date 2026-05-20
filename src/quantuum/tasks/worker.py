from aiogram import Bot
from arq.connections import RedisSettings

from quantuum.db.session import get_sessionmaker
from quantuum.logging_setup import configure_logging
from quantuum.settings import get_settings
from quantuum.tasks.blueprint import blueprint_generate
from quantuum.tasks.provision import provision_tenant


async def startup(ctx) -> None:
    configure_logging()
    settings = get_settings()
    ctx["sessionmaker"] = get_sessionmaker()
    ctx["bot"] = Bot(token=settings.bot_token) if settings.bot_token else None
    ctx["master_bot"] = Bot(token=settings.master_bot_token) if settings.master_bot_token else None


async def shutdown(ctx) -> None:
    for key in ("bot", "master_bot"):
        bot: Bot = ctx.get(key)
        if bot is not None:
            await bot.session.close()


class WorkerSettings:
    functions = [blueprint_generate, provision_tenant]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
