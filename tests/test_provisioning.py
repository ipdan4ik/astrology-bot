from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.db.models import TenantBot
from quantuum.domain.invites import create_invite
from quantuum.domain.provisioning import create_tenant_from_onboarding, master_can_manage_bots


async def test_master_can_manage_bots_reads_get_me():
    on = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(can_manage_bots=True)))
    off = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(can_manage_bots=False)))
    missing = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace()))
    assert await master_can_manage_bots(on) is True
    assert await master_can_manage_bots(off) is False
    assert await master_can_manage_bots(missing) is False


async def test_create_tenant_from_onboarding(session):
    invite = await create_invite(session, created_by_account_id=None, tier="basic", max_uses=1)
    tenant = await create_tenant_from_onboarding(
        session,
        invite=invite,
        slug="acme",
        display_name="Acme Astro",
        default_lang="ru",
        owner_tg_id=12345,
        owner_chat_id=12345,
    )
    assert tenant.status == "provisioning"
    assert tenant.tier == "basic"
    assert tenant.owner_tg_id == "12345"
    assert tenant.owner_chat_id == "12345"

    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant.id))
    tb = result.scalar_one()
    assert tb.status == "provisioning"
    assert tb.webhook_secret_path
    assert tb.bot_telegram_id is None

    await session.refresh(invite)
    assert invite.used_count == 1
    assert invite.status == "used"


async def test_create_tenant_multiuse_invite_stays_active(session):
    invite = await create_invite(session, created_by_account_id=None, max_uses=2)
    await create_tenant_from_onboarding(
        session, invite=invite, slug="a1", display_name="A1",
        default_lang="ru", owner_tg_id=1, owner_chat_id=1,
    )
    await session.refresh(invite)
    assert invite.used_count == 1
    assert invite.status == "active"


async def test_finalize_provisioning_activates_tenant(session):
    from quantuum.common.crypto import decrypt_token
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding, finalize_provisioning
    from quantuum.domain.tenants import account_has_role
    from quantuum.db.models import Account

    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )

    tb = await finalize_provisioning(
        session,
        tenant_id=tenant.id,
        token="900:newbottoken",
        bot_telegram_id=900,
        bot_username="zen_bot",
        default_lang="ru",
    )
    assert tb.status == "active"
    assert tb.bot_telegram_id == 900
    assert tb.bot_username == "zen_bot"
    assert decrypt_token(tb.bot_token_enc) == "900:newbottoken"

    await session.refresh(tenant)
    assert tenant.status == "active"
    assert tenant.primary_owner_account_id is not None

    owner = await session.get(Account, tenant.primary_owner_account_id)
    assert owner.tenant_id == tenant.id
    assert await account_has_role(session, tenant_id=tenant.id, account_id=owner.id, role="owner")


async def test_validate_bot_token_rejects_garbage(monkeypatch):
    from quantuum.domain import provisioning

    assert await provisioning.validate_bot_token("not-a-token") is None
