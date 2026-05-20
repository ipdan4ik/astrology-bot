import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_bot, create_dispatcher
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update

logger = get_logger("bot.runner")


async def process_one_update(dp: Dispatcher, bot: Bot, update: dict) -> None:
    await dp.feed_raw_update(bot=bot, update=update)


async def run() -> None:
    configure_logging()
    bot = create_bot()
    dp = create_dispatcher()
    logger.info("bot_runner_started")
    while True:
        update = await pop_update(timeout=5)
        if update is None:
            continue
        try:
            await process_one_update(dp, bot, update)
        except Exception:  # keep the loop alive
            logger.exception("update_processing_failed", update_id=update.get("update_id"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
