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

    # Invite use is now consumed at finalize, not at create (abandoned onboarding
    # leaves the invite usable).
    await session.refresh(invite)
    assert invite.used_count == 0
    assert invite.status == "active"


async def test_create_tenant_multiuse_invite_stays_active(session):
    invite = await create_invite(session, created_by_account_id=None, max_uses=2)
    await create_tenant_from_onboarding(
        session, invite=invite, slug="a1", display_name="A1",
        default_lang="ru", owner_tg_id=1, owner_chat_id=1,
    )
    # Create no longer consumes the invite.
    await session.refresh(invite)
    assert invite.used_count == 0
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

    # The chosen default language is seeded so the new tenant's bot serves it (not the
    # English fallback). Regression: seed_tenant_defaults was a no-op placeholder.
    from quantuum.db.models import TenantLanguage

    langs = (
        await session.execute(select(TenantLanguage).where(TenantLanguage.tenant_id == tenant.id))
    ).scalars().all()
    default = [r.lang for r in langs if r.is_default]
    assert default == ["ru"]
    assert all(r.enabled for r in langs)


async def test_validate_bot_token_rejects_garbage(monkeypatch):
    from quantuum.domain import provisioning

    assert await provisioning.validate_bot_token("not-a-token") is None


async def test_tenant_has_invite_id_column(session, default_tenant):
    from quantuum.db.models import Tenant

    t = await session.get(Tenant, default_tenant.id)
    # column exists and defaults to None
    assert hasattr(t, "invite_id")
    assert t.invite_id is None


async def test_create_onboarding_does_not_consume_invite(session):
    invite = await create_invite(session, created_by_account_id=None, max_uses=1)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="cabbage", display_name="Cabbage",
        default_lang="en", owner_tg_id=111, owner_chat_id=111,
    )
    await session.refresh(invite)
    assert invite.used_count == 0          # NOT consumed at start
    assert invite.status == "active"
    assert tenant.invite_id == invite.id   # linked


async def test_finalize_consumes_invite(session):
    from quantuum.domain.provisioning import finalize_provisioning

    invite = await create_invite(session, created_by_account_id=None, max_uses=1)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="kale", display_name="Kale",
        default_lang="en", owner_tg_id=222, owner_chat_id=222,
    )
    await finalize_provisioning(
        session, tenant_id=tenant.id, token="123456:ABC-DEF",
        bot_telegram_id=500001, bot_username="kalebot", default_lang="en",
    )
    await session.refresh(invite)
    assert invite.used_count == 1
    assert invite.status == "used"


async def test_second_onboarding_reuses_provisioning_tenant(session):
    invite = await create_invite(session, created_by_account_id=None, max_uses=1)
    t1 = await create_tenant_from_onboarding(
        session, invite=invite, slug="leek1", display_name="Leek",
        default_lang="en", owner_tg_id=333, owner_chat_id=333,
    )
    t2 = await create_tenant_from_onboarding(
        session, invite=invite, slug="leek2", display_name="Leek2",
        default_lang="en", owner_tg_id=333, owner_chat_id=333,
    )
    assert t2.id == t1.id            # reused, not duplicated
    assert t2.slug == "leek2"        # details updated to latest attempt
    from sqlalchemy import func, select
    from quantuum.db.models import Tenant, TenantBot
    n_tenants = (await session.execute(
        select(func.count()).select_from(Tenant).where(Tenant.invite_id == invite.id)
    )).scalar()
    n_bots = (await session.execute(
        select(func.count()).select_from(TenantBot).where(TenantBot.tenant_id == t1.id)
    )).scalar()
    assert n_tenants == 1 and n_bots == 1


async def test_finalize_rejects_bot_already_in_use(session):
    import pytest
    from quantuum.db.models import Tenant, TenantBot
    from quantuum.domain.provisioning import (
        BotAlreadyInUseError, finalize_provisioning,
    )
    # tenant A already active with bot id 600001
    a = Tenant(slug="taken", display_name="Taken", status="active",
               owner_tg_id="900", owner_chat_id="900")
    session.add(a); await session.flush()
    session.add(TenantBot(
        tenant_id=a.id, bot_token_enc=b"x", transport="polling",
        webhook_secret_path="s1", status="active", bot_telegram_id=600001,
    ))
    # tenant B provisioning, trying to claim the SAME bot id
    b = Tenant(slug="claimer", display_name="Claimer", status="provisioning",
               owner_tg_id="901", owner_chat_id="901")
    session.add(b); await session.flush()
    session.add(TenantBot(
        tenant_id=b.id, bot_token_enc=b"", transport="polling",
        webhook_secret_path="s2", status="provisioning",
    ))
    await session.commit()

    with pytest.raises(BotAlreadyInUseError):
        await finalize_provisioning(
            session, tenant_id=b.id, token="123456:ABC-DEF",
            bot_telegram_id=600001, bot_username="dupe", default_lang="en",
        )
    # B not activated
    b2 = await session.get(Tenant, b.id); await session.refresh(b2)
    assert b2.status == "provisioning"
