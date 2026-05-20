"""Local/dev long-polling entrypoint: polls every active polling-transport bot."""

import asyncio

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger

logger = get_logger("bot.polling")


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        rows = await list_active_tenant_bots(session, transport="polling")
    pool = build_bots(rows)
    dp = create_dispatcher()
    for bot in pool.values():
        await bot.delete_webhook(drop_pending_updates=True)
    logger.info("bot_polling_started", polling_bots=len(pool))
    if not pool:
        logger.warning("no_polling_bots_configured")
        return
    await dp.start_polling(*pool.values())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
