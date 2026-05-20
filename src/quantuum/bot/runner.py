import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update

logger = get_logger("bot.runner")


async def process_one_envelope(dp: Dispatcher, pool: dict[int, Bot], envelope: dict) -> None:
    bot = pool.get(envelope["bot_id"])
    if bot is None:
        logger.warning("update_for_unknown_bot", bot_id=envelope["bot_id"])
        return
    await dp.feed_raw_update(bot=bot, update=envelope["update"])


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        rows = await list_active_tenant_bots(session, transport="webhook")
    pool = build_bots(rows)
    dp = create_dispatcher()
    logger.info("bot_runner_started", webhook_bots=len(pool))
    while True:
        envelope = await pop_update(timeout=5)
        if envelope is None:
            continue
        try:
            await process_one_envelope(dp, pool, envelope)
        except Exception:
            logger.exception("update_processing_failed", bot_id=envelope.get("bot_id"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
