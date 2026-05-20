from unittest.mock import AsyncMock

from quantuum.bot import polling


async def test_start_deletes_webhook_then_polls():
    bot = AsyncMock()
    dp = AsyncMock()
    await polling.start(bot, dp)
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    dp.start_polling.assert_awaited_once_with(bot)
