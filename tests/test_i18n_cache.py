"""Tests for quantuum.i18n.cache — Redis hash cache for i18n strings."""
import pytest

from quantuum.db.models import PlatformString, TenantLanguage
from quantuum.i18n import cache as i18n_cache
from quantuum.i18n.cache import get_cached_strings, invalidate_i18n
from quantuum.i18n.resolver import t
from quantuum.redis_client import get_redis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed(session, tenant_id: int, *, lang: str = "en"):
    """Seed one PlatformString and make *lang* the tenant default."""
    session.add(PlatformString(key="hello", lang=lang, text="Hello World"))
    session.add(
        TenantLanguage(tenant_id=tenant_id, lang=lang, enabled=True, is_default=True)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# test_cache_built_then_hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_built_then_hit(session, default_tenant, monkeypatch):
    """First call builds from DB (merged_strings called once); second call is
    served from Redis (merged_strings NOT called again). __loaded__ must not
    appear in the returned dict."""
    await get_redis().flushdb()
    await _seed(session, default_tenant.id)

    call_count = 0
    original_merged = i18n_cache.merged_strings

    async def counting_merged(sess, tid, lng):
        nonlocal call_count
        call_count += 1
        return await original_merged(sess, tid, lng)

    monkeypatch.setattr(i18n_cache, "merged_strings", counting_merged)

    # First call — cold cache, must hit DB
    result1 = await get_cached_strings(session, default_tenant.id, "en")
    assert call_count == 1
    assert result1 == {"hello": "Hello World"}
    assert "__loaded__" not in result1

    # Second call — warm cache, must NOT hit DB
    result2 = await get_cached_strings(session, default_tenant.id, "en")
    assert call_count == 1  # still 1, no rebuild
    assert result2 == {"hello": "Hello World"}
    assert "__loaded__" not in result2


# ---------------------------------------------------------------------------
# test_invalidate_rebuilds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_rebuilds(session, default_tenant, monkeypatch):
    """After invalidation, the next get_cached_strings call rebuilds from DB."""
    await get_redis().flushdb()
    await _seed(session, default_tenant.id)

    call_count = 0
    original_merged = i18n_cache.merged_strings

    async def counting_merged(sess, tid, lng):
        nonlocal call_count
        call_count += 1
        return await original_merged(sess, tid, lng)

    monkeypatch.setattr(i18n_cache, "merged_strings", counting_merged)

    # Warm up cache
    await get_cached_strings(session, default_tenant.id, "en")
    assert call_count == 1

    # Invalidate
    await invalidate_i18n(default_tenant.id, "en")

    # Should rebuild
    result = await get_cached_strings(session, default_tenant.id, "en")
    assert call_count == 2
    assert result == {"hello": "Hello World"}


# ---------------------------------------------------------------------------
# test_t_uses_cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t_uses_cache(session, default_tenant, monkeypatch):
    """resolver.t() uses the cache: same (tenant, lang) is only built once
    from DB across two consecutive calls for the same key."""
    await get_redis().flushdb()
    await _seed(session, default_tenant.id)

    call_count = 0
    original_merged = i18n_cache.merged_strings

    async def counting_merged(sess, tid, lng):
        nonlocal call_count
        call_count += 1
        return await original_merged(sess, tid, lng)

    monkeypatch.setattr(i18n_cache, "merged_strings", counting_merged)

    # First call via resolver
    result1 = await t(session, "hello", "en", tenant_id=default_tenant.id)
    assert result1 == "Hello World"
    # DB should have been called once (for "en")
    assert call_count == 1

    # Second call via resolver — cache should serve it
    result2 = await t(session, "hello", "en", tenant_id=default_tenant.id)
    assert result2 == "Hello World"
    assert call_count == 1  # still 1, no rebuild
