from unittest.mock import AsyncMock

from quantuum.domain.invites import create_invite
from quantuum.domain.provisioning import create_tenant_from_onboarding
from quantuum.tasks.provision import provision_tenant


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


async def test_provision_falls_back_to_manual_token(session):
    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="fb", display_name="FB",
        default_lang="ru", owner_tg_id=42, owner_chat_id=42,
    )
    master_bot = AsyncMock()
    ctx = {"sessionmaker": _Maker(session), "master_bot": master_bot}

    await provision_tenant(ctx, tenant.id)

    await session.refresh(tenant)
    assert tenant.status == "awaiting_manual_token"
    master_bot.send_message.assert_awaited_once()
    chat_id, _text = master_bot.send_message.await_args.args
    assert chat_id == 42


async def test_provision_unknown_tenant_is_safe(session):
    ctx = {"sessionmaker": _Maker(session), "master_bot": AsyncMock()}
    await provision_tenant(ctx, 999999)  # no exception
