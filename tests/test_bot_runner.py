from unittest.mock import AsyncMock

from quantuum.bot.runner import process_one_update


async def test_process_one_update_feeds_dispatcher():
    dp = AsyncMock()
    bot = AsyncMock()
    update = {"update_id": 1, "message": {"message_id": 1, "text": "hi"}}
    await process_one_update(dp, bot, update)
    dp.feed_raw_update.assert_awaited_once()
    args, kwargs = dp.feed_raw_update.await_args
    assert kwargs.get("bot") is bot or bot in args
