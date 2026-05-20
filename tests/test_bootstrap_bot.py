from sqlmodel import select

from quantuum.common.crypto import decrypt_token
from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
from quantuum.db.models import TenantBot


async def test_ensure_default_tenant_bot_idempotent(session, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "777:secrettoken")
    from quantuum.settings import get_settings
    get_settings.cache_clear()

    tenant = await ensure_default_tenant(session)
    await ensure_default_tenant_bot(session)
    await ensure_default_tenant_bot(session)  # idempotent

    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant.id))
    bots = result.scalars().all()
    assert len(bots) == 1
    tb = bots[0]
    assert tb.bot_telegram_id == 777
    assert decrypt_token(tb.bot_token_enc) == "777:secrettoken"
    get_settings.cache_clear()
