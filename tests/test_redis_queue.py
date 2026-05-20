import pytest_asyncio

from quantuum import redis_client


@pytest_asyncio.fixture
async def redis():
    client = redis_client.get_redis()
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


async def test_push_and_pop_update(redis):
    await redis_client.push_update(555, {"update_id": 1, "text": "hi"})
    item = await redis_client.pop_update(timeout=1)
    assert item == {"bot_id": 555, "update": {"update_id": 1, "text": "hi"}}


async def test_pop_returns_none_on_timeout(redis):
    item = await redis_client.pop_update(timeout=1)
    assert item is None
