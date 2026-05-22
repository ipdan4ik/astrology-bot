import uuid

from quantuum.db.models import Tenant, TenantBot


async def _make_tenant_with_bot(session, *, slug, bot_tg_id):
    tenant = Tenant(slug=slug, display_name=slug.title())
    session.add(tenant)
    await session.flush()
    bot = TenantBot(
        tenant_id=tenant.id,
        bot_telegram_id=bot_tg_id,
        bot_username=f"{slug}bot",
        bot_token_enc=b"x",
        webhook_secret_path=f"wh-{uuid.uuid4().hex}",
        status="active",
    )
    session.add(bot)
    await session.commit()
    await session.refresh(tenant)
    await session.refresh(bot)
    return tenant, bot


async def test_archive_tenant_tombstones(session):
    from quantuum.domain.tenants import archive_tenant

    tenant, bot = await _make_tenant_with_bot(session, slug="acme", bot_tg_id=12345)
    tid = tenant.id

    result = await archive_tenant(session, tid)
    await session.commit()

    await session.refresh(tenant)
    await session.refresh(bot)
    assert result is not None
    assert tenant.status == "archived"
    assert tenant.slug == f"acme__del{tid}"
    assert bot.bot_telegram_id is None
    assert bot.status == "archived"


async def test_archive_tenant_idempotent(session):
    from quantuum.domain.tenants import archive_tenant

    tenant, _bot = await _make_tenant_with_bot(session, slug="beta", bot_tg_id=222)
    tid = tenant.id

    await archive_tenant(session, tid)
    await session.commit()
    await session.refresh(tenant)
    first_slug = tenant.slug

    # Second call must not re-tombstone the (already tombstoned) slug.
    await archive_tenant(session, tid)
    await session.commit()
    await session.refresh(tenant)
    assert tenant.slug == first_slug


async def test_archive_tenant_missing_returns_none(session):
    from quantuum.domain.tenants import archive_tenant

    assert await archive_tenant(session, 999999) is None


async def test_archive_frees_slug_and_bot_for_recreation(session):
    """The core re-creation guarantee: after archiving, the same slug AND the same
    bot_telegram_id can be reused by a fresh tenant with no unique violation."""
    from quantuum.domain.tenants import archive_tenant

    _tenant, _bot = await _make_tenant_with_bot(session, slug="gamma", bot_tg_id=777)
    await archive_tenant(session, _tenant.id)
    await session.commit()

    # Re-create with the SAME slug and SAME bot_telegram_id — must not raise.
    new_tenant, new_bot = await _make_tenant_with_bot(session, slug="gamma", bot_tg_id=777)
    assert new_tenant.id != _tenant.id
    assert new_bot.bot_telegram_id == 777
    assert new_tenant.slug == "gamma"
