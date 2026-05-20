from sqlmodel import select

from quantuum.db.models import TenantBot
from quantuum.domain.invites import create_invite
from quantuum.domain.provisioning import create_tenant_from_onboarding, try_programmatic_create


async def test_try_programmatic_create_returns_none():
    assert await try_programmatic_create(slug="x", display_name="X") is None


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
