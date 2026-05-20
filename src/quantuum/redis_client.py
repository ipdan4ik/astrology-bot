import json

import redis.asyncio as aioredis

from quantuum.settings import get_settings

_redis: aioredis.Redis | None = None
UPDATE_QUEUE_KEY = "tg:updates"


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def push_update(update: dict) -> None:
    await get_redis().rpush(UPDATE_QUEUE_KEY, json.dumps(update))


async def pop_update(timeout: int = 5) -> dict | None:
    result = await get_redis().blpop([UPDATE_QUEUE_KEY], timeout=timeout)
    if result is None:
        return None
    _, payload = result
    return json.loads(payload)
