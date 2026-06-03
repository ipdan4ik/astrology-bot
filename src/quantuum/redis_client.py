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


DEDUP_TTL_SECONDS = 3600


async def mark_update_seen(bot_id: int, update_id: int) -> bool:
    """Return True if this (bot_id, update_id) is NEW (claim it), False if already seen.

    Uses SETNX with a TTL so replayed/duplicate Telegram deliveries are dropped.
    A missing update_id (None) is always treated as new (cannot dedup).
    """
    if update_id is None:
        return True
    key = f"tg:dedup:{bot_id}:{update_id}"
    created = await get_redis().set(key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
    return bool(created)


async def push_update(bot_id: int, update: dict) -> None:
    await get_redis().rpush(UPDATE_QUEUE_KEY, json.dumps({"bot_id": bot_id, "update": update}))


async def pop_update(timeout: int = 5) -> dict | None:
    result = await get_redis().blpop([UPDATE_QUEUE_KEY], timeout=timeout)
    if result is None:
        return None
    _, payload = result
    return json.loads(payload)


BOT_RELOAD_CHANNEL = "bot:reload"


async def publish_bot_reload() -> None:
    """Nudge the bot workers to reconcile their bot pools immediately."""
    await get_redis().publish(BOT_RELOAD_CHANNEL, "1")
