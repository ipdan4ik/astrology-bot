from unittest.mock import AsyncMock

from quantuum.bot.runner import WebhookConsumer


def _consumer(customer_pool, master_pool):
    return WebhookConsumer(
        customer_dp=AsyncMock(),
        master_dp=AsyncMock(),
        customer_pool=customer_pool,
        master_pool=master_pool,
    )


async def test_routes_customer_bot_to_customer_dp():
    bot = AsyncMock()
    c = _consumer({42: bot}, {})
    await c.process({"bot_id": 42, "update": {"update_id": 1}})
    c.customer_dp.feed_raw_update.assert_awaited_once()
    c.master_dp.feed_raw_update.assert_not_awaited()
    _, kwargs = c.customer_dp.feed_raw_update.await_args
    assert kwargs["bot"] is bot


async def test_routes_master_bot_to_master_dp():
    bot = AsyncMock()
    c = _consumer({}, {7: bot})
    await c.process({"bot_id": 7, "update": {"update_id": 1}})
    c.master_dp.feed_raw_update.assert_awaited_once()
    c.customer_dp.feed_raw_update.assert_not_awaited()


async def test_skips_unknown_bot():
    c = _consumer({}, {})
    await c.process({"bot_id": 99, "update": {"update_id": 1}})
    c.customer_dp.feed_raw_update.assert_not_awaited()
    c.master_dp.feed_raw_update.assert_not_awaited()
