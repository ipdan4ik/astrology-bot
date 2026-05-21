from sqlmodel import select

from quantuum.db.models import PaymentProvider
from quantuum.domain.providers import ensure_stars_provider, get_active_provider


async def test_ensure_stars_provider_idempotent(session, default_tenant):
    p1 = await ensure_stars_provider(session, default_tenant.id)
    p2 = await ensure_stars_provider(session, default_tenant.id)
    assert p1.id == p2.id
    assert p1.kind == "tg_stars"

    result = await session.execute(
        select(PaymentProvider).where(PaymentProvider.tenant_id == default_tenant.id)
    )
    assert len(result.scalars().all()) == 1


async def test_get_active_provider(session, default_tenant):
    assert await get_active_provider(session, default_tenant.id) is None
    created = await ensure_stars_provider(session, default_tenant.id)
    got = await get_active_provider(session, default_tenant.id)
    assert got is not None and got.id == created.id


async def test_ensure_platform_stars_provider(session):
    from quantuum.db.bootstrap import ensure_platform_stars_provider, ensure_platform_tenant

    platform = await ensure_platform_tenant(session)
    await ensure_platform_stars_provider(session)
    got = await get_active_provider(session, platform.id)
    assert got is not None and got.kind == "tg_stars"
