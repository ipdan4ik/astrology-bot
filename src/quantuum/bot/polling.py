"""Local/dev long-polling entrypoint: customer bots + master bot on separate dispatchers."""

import asyncio

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.db.bootstrap import (
    ensure_base_strings,
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_master_bot,
    ensure_platform_stars_provider,
    ensure_platform_tenant,
    ensure_tenant_default_language,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_default_tenant_id, get_platform_tenant_id, list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger

logger = get_logger("bot.polling")


async def split_by_platform(session, rows):
    """Split tenant_bots rows into (master_rows, customer_rows) by tenant.is_platform."""
    platform_id = await get_platform_tenant_id(session)
    master_rows = [r for r in rows if r.tenant_id == platform_id]
    customer_rows = [r for r in rows if r.tenant_id != platform_id]
    return master_rows, customer_rows


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        platform = await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_platform_stars_provider(session)
        await ensure_base_strings(session)
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")
        rows = await list_active_tenant_bots(session, transport="polling")
        master_rows, customer_rows = await split_by_platform(session, rows)

    customer_pool = build_bots(customer_rows)
    master_pool = build_bots(master_rows)
    customer_dp = create_dispatcher()
    master_dp = create_master_dispatcher()

    for bot in list(customer_pool.values()) + list(master_pool.values()):
        await bot.delete_webhook(drop_pending_updates=True)

    logger.info("bot_polling_started", customer_bots=len(customer_pool), master_bots=len(master_pool))

    tasks = []
    if customer_pool:
        tasks.append(customer_dp.start_polling(*customer_pool.values(), handle_signals=False))
    if master_pool:
        tasks.append(master_dp.start_polling(*master_pool.values(), handle_signals=False))
    if not tasks:
        logger.warning("no_polling_bots_configured")
        return
    await asyncio.gather(*tasks)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
