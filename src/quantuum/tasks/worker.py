from aiogram import Bot
from arq import cron
from arq.connections import RedisSettings

from quantuum.db.session import get_sessionmaker
from quantuum.llm.registry import get_llm_client
from quantuum.logging_setup import configure_logging
from quantuum.settings import get_settings
from quantuum.tasks.blueprint import blueprint_generate
from quantuum.tasks.lifecycle import subscription_lifecycle
from quantuum.tasks.provision import provision_tenant
from quantuum.tasks.qa import qa_generate
from quantuum.tasks.daily import daily_generate
from quantuum.tasks.transits import transit_generate


async def startup(ctx) -> None:
    configure_logging()
    settings = get_settings()
    ctx["sessionmaker"] = get_sessionmaker()
    ctx["bot"] = Bot(token=settings.bot_token) if settings.bot_token else None
    ctx["master_bot"] = Bot(token=settings.master_bot_token) if settings.master_bot_token else None
    ctx["llm_client"] = get_llm_client(settings)


async def shutdown(ctx) -> None:
    for key in ("bot", "master_bot"):
        bot: Bot = ctx.get(key)
        if bot is not None:
            await bot.session.close()


class WorkerSettings:
    functions = [blueprint_generate, provision_tenant, subscription_lifecycle, qa_generate, transit_generate, daily_generate]
    cron_jobs = [cron(subscription_lifecycle, minute=0)]  # top of every hour
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
