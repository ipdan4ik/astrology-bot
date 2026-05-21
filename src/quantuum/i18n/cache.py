"""Redis hash cache for i18n strings.

Each (tenant_id, lang) pair is stored as a Redis hash at key ``i18n:<tenant_id>:<lang>``.
A special ``__loaded__`` field (value ``"1"``) marks that the hash was fully built from
the DB, so a hash with zero real keys is still distinguishable from a cold cache.
"""
import json

from quantuum.i18n.strings import merged_strings
from quantuum.redis_client import get_redis

_TTL = 3600
_MARKER = "__loaded__"


def _cache_key(tenant_id: int, lang: str) -> str:
    return f"i18n:{tenant_id}:{lang}"


async def get_cached_strings(session, tenant_id: int, lang: str) -> dict[str, str]:
    """Return the merged {key: text} for (tenant, lang), via a Redis hash cache.

    Builds from DB on cold cache; the ``__loaded__`` marker distinguishes a
    built-but-key-absent cache from a cold one (so a genuinely missing key
    never triggers a rebuild).
    """
    r = get_redis()
    ckey = _cache_key(tenant_id, lang)
    cached = await r.hgetall(ckey)
    if cached.get(_MARKER) == "1":
        cached.pop(_MARKER, None)
        return cached
    # cold: build from DB
    data = await merged_strings(session, tenant_id, lang)
    mapping = {**data, _MARKER: "1"}
    await r.hset(ckey, mapping=mapping)
    await r.expire(ckey, _TTL)
    return data


async def invalidate_i18n(tenant_id: int, lang: str | None = None) -> None:
    """Drop cached strings for a tenant (one lang, or all langs when lang is None),
    then publish an i18n_invalidate event (consumers added in Plan 5b)."""
    r = get_redis()
    if lang is not None:
        await r.delete(_cache_key(tenant_id, lang))
    else:
        # delete all langs for this tenant
        pattern = f"i18n:{tenant_id}:*"
        async for k in r.scan_iter(match=pattern):
            await r.delete(k)
    await r.publish("i18n_invalidate", json.dumps({"tenant_id": tenant_id, "lang": lang}))
