from unittest.mock import AsyncMock

from quantuum.bot.runner import process_one_envelope


async def test_process_one_envelope_dispatches_with_pooled_bot():
    dp = AsyncMock()
    bot = AsyncMock()
    pool = {42: bot}
    await process_one_envelope(dp, pool, {"bot_id": 42, "update": {"update_id": 1}})
    dp.feed_raw_update.assert_awaited_once()
    _, kwargs = dp.feed_raw_update.await_args
    assert kwargs["bot"] is bot


async def test_process_one_envelope_skips_unknown_bot():
    dp = AsyncMock()
    await process_one_envelope(dp, {}, {"bot_id": 99, "update": {"update_id": 1}})
    dp.feed_raw_update.assert_not_awaited()
