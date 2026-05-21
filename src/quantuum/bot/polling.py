"""Local/dev long-polling entrypoint: customer + master bots, hot-reloaded without restart."""

import asyncio

from quantuum.bot.app import create_dispatcher
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.bot.reload import PollingSupervisor, reload_signals
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
from quantuum.domain.tenants import get_default_tenant_id
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.settings import get_settings

logger = get_logger("bot.polling")


async def run() -> None:
    configure_logging()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        platform = await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_platform_stars_provider(session)
        await ensure_base_strings(session)
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")

    supervisor = PollingSupervisor(
        sessionmaker,
        customer_dp=create_dispatcher(),
        master_dp=create_master_dispatcher(),
    )
    await supervisor.reconcile()
    logger.info("bot_polling_started", bots=len(supervisor.live))
    interval = get_settings().bot_reload_interval_seconds
    while True:
        try:
            async for _ in reload_signals(interval):
                try:
                    await supervisor.reconcile()
                except Exception:
                    logger.exception("polling_reconcile_failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reload_signals_failed_retrying")
            await asyncio.sleep(interval)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
