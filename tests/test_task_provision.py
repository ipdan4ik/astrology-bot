from types import SimpleNamespace
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


def _master_bot(*, can_manage: bool) -> AsyncMock:
    bot = AsyncMock()
    bot.get_me = AsyncMock(return_value=SimpleNamespace(can_manage_bots=can_manage))
    return bot


async def test_provision_uses_managed_bot_when_capable(session):
    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="acme", display_name="Acme",
        default_lang="ru", owner_tg_id=42, owner_chat_id=42,
    )
    master_bot = _master_bot(can_manage=True)
    ctx = {"sessionmaker": _Maker(session), "master_bot": master_bot}

    await provision_tenant(ctx, tenant.id)

    await session.refresh(tenant)
    assert tenant.status == "awaiting_managed_bot"
    master_bot.send_message.assert_awaited_once()
    chat_id = master_bot.send_message.await_args.args[0]
    kb = master_bot.send_message.await_args.kwargs["reply_markup"]
    button = kb.keyboard[0][0]
    assert chat_id == 42
    assert button.request_managed_bot is not None
    assert button.request_managed_bot.suggested_username == "acme_bot"
    assert button.request_managed_bot.suggested_name == "Acme"


async def test_provision_falls_back_to_manual_token(session):
    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()  # create_invite now flushes; commit so the provision task sees it
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="fb", display_name="FB",
        default_lang="ru", owner_tg_id=42, owner_chat_id=42,
    )
    master_bot = _master_bot(can_manage=False)
    ctx = {"sessionmaker": _Maker(session), "master_bot": master_bot}

    await provision_tenant(ctx, tenant.id)

    await session.refresh(tenant)
    assert tenant.status == "awaiting_manual_token"
    master_bot.send_message.assert_awaited_once()
    chat_id, _text = master_bot.send_message.await_args.args
    assert chat_id == 42


async def test_provision_unknown_tenant_is_safe(session):
    ctx = {"sessionmaker": _Maker(session), "master_bot": _master_bot(can_manage=False)}
    await provision_tenant(ctx, 999999)  # no exception
