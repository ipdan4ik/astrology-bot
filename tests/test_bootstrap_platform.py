from sqlmodel import select

from quantuum.common.crypto import decrypt_token
from quantuum.db.bootstrap import ensure_master_bot, ensure_platform_tenant, ensure_superadmin
from quantuum.db.models import Account, AccountIdentity, TenantBot
from quantuum.domain.tenants import get_platform_tenant_id
from quantuum.settings import get_settings


async def test_ensure_platform_tenant_idempotent(session):
    t1 = await ensure_platform_tenant(session)
    t2 = await ensure_platform_tenant(session)
    assert t1.id == t2.id
    assert t1.is_platform is True
    assert t1.slug == "platform"
    assert await get_platform_tenant_id(session) == t1.id


async def test_ensure_master_bot_creates_row(session, monkeypatch):
    monkeypatch.setenv("MASTER_BOT_TOKEN", "888:masters")
    monkeypatch.setenv("MASTER_BOT_USERNAME", "quantuum_master_bot")
    get_settings.cache_clear()

    await ensure_master_bot(session)
    await ensure_master_bot(session)  # idempotent

    platform_id = await get_platform_tenant_id(session)
    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == platform_id))
    bots = result.scalars().all()
    assert len(bots) == 1
    assert bots[0].bot_telegram_id == 888
    assert bots[0].bot_username == "quantuum_master_bot"
    assert decrypt_token(bots[0].bot_token_enc) == "888:masters"
    get_settings.cache_clear()


async def test_ensure_master_bot_noop_without_token(session, monkeypatch):
    monkeypatch.setenv("MASTER_BOT_TOKEN", "")
    get_settings.cache_clear()
    await ensure_master_bot(session)
    platform_id = await get_platform_tenant_id(session)
    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == platform_id))
    assert result.scalars().first() is None
    get_settings.cache_clear()


async def test_ensure_superadmin_creates_account(session, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_EMAIL", "root@quantuum.example")
    get_settings.cache_clear()

    await ensure_superadmin(session)
    await ensure_superadmin(session)  # idempotent

    result = await session.execute(
        select(Account).where(Account.is_superadmin == True)  # noqa: E712
    )
    admins = result.scalars().all()
    assert len(admins) == 1
    assert admins[0].tenant_id is None
    ident = await session.execute(
        select(AccountIdentity).where(AccountIdentity.email == "root@quantuum.example")
    )
    assert ident.scalar_one().provider == "magic_link"
    get_settings.cache_clear()
