from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import TenantBot
from quantuum.domain.tenants import (
    account_has_role,
    grant_role,
    get_tenant_bot_by_webhook_secret,
    list_active_tenant_bots,
    resolve_tenant_id_by_bot,
)


async def _bot(session, tenant_id, *, bot_id, secret, transport="polling", status="active"):
    tb = TenantBot(
        tenant_id=tenant_id, bot_telegram_id=bot_id, bot_token_enc=b"enc",
        webhook_secret_path=secret, transport=transport, status=status,
    )
    session.add(tb)
    await session.commit()
    await session.refresh(tb)
    return tb


async def test_resolve_tenant_id_by_bot(session, default_tenant):
    await _bot(session, default_tenant.id, bot_id=111, secret="s1")
    assert await resolve_tenant_id_by_bot(session, 111) == default_tenant.id
    assert await resolve_tenant_id_by_bot(session, 999) is None


async def test_get_tenant_bot_by_webhook_secret(session, default_tenant):
    await _bot(session, default_tenant.id, bot_id=222, secret="abc")
    tb = await get_tenant_bot_by_webhook_secret(session, "abc")
    assert tb is not None and tb.bot_telegram_id == 222
    assert await get_tenant_bot_by_webhook_secret(session, "nope") is None


async def test_list_active_tenant_bots_filters(session, default_tenant):
    await _bot(session, default_tenant.id, bot_id=1, secret="a", transport="polling")
    await _bot(session, default_tenant.id, bot_id=2, secret="b", transport="webhook")
    await _bot(session, default_tenant.id, bot_id=3, secret="c", transport="polling", status="paused")
    polling = await list_active_tenant_bots(session, transport="polling")
    assert {tb.bot_telegram_id for tb in polling} == {1}
    all_active = await list_active_tenant_bots(session)
    assert {tb.bot_telegram_id for tb in all_active} == {1, 2}


async def test_roles(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="5")
    assert await account_has_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner") is False
    await grant_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner")
    assert await account_has_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner") is True
    await grant_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner")  # idempotent


async def test_resolve_large_bot_id_no_int4_overflow(session, default_tenant):
    big = 7123456789  # exceeds int4 max (2,147,483,647) — must be BigInteger
    await _bot(session, default_tenant.id, bot_id=big, secret="big-bot")
    assert await resolve_tenant_id_by_bot(session, big) == default_tenant.id
