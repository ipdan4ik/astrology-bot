"""Local/dev long-polling entrypoint for the bot-worker.

Plan 1 delivers updates via webhook -> Redis queue -> runner. For local
development without a public URL, this entrypoint runs aiogram long polling
directly against Telegram, reusing the same dispatcher (middleware + handlers).

Run: `python -m quantuum.bot.polling`
"""

import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_bot, create_dispatcher
from quantuum.db.bootstrap import ensure_default_tenant
from quantuum.db.session import get_sessionmaker
from quantuum.logging_setup import configure_logging, get_logger

logger = get_logger("bot.polling")


async def start(bot: Bot, dp: Dispatcher) -> None:
    # Drop any webhook so Telegram lets us long-poll; clear backlog.
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("bot_polling_started")
    await dp.start_polling(bot)


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
    bot = create_bot()
    dp = create_dispatcher()
    await start(bot, dp)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
