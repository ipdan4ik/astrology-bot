from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.bot.handlers.master_onboarding import slug_is_available


async def test_slug_is_available(session, default_tenant):
    assert await slug_is_available(session, "brand-new") is True
    assert await slug_is_available(session, "default") is False


def test_master_cancel_kb_uses_owner_callback():
    from quantuum.bot.handlers.master_onboarding import master_cancel_kb
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    kb = master_cancel_kb()
    cb = kb.inline_keyboard[0][0].callback_data
    assert OwnerOnboardCb.unpack(cb).action == "cancel"


def test_owner_onboard_callback_roundtrip():
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    packed = OwnerOnboardCb(action="confirm").pack()
    assert OwnerOnboardCb.unpack(packed).action == "confirm"


class _FakeState:
    def __init__(self, data):
        self._data = dict(data)
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self._data = {}
        self.state = None


def _patch_sessionmaker(monkeypatch, module, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(module, "get_sessionmaker", lambda: _Maker())


async def test_confirm_creates_tenant_and_enqueues(session, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb
    from quantuum.db.models import Tenant
    from quantuum.domain.invites import create_invite

    _patch_sessionmaker(monkeypatch, mo, session)
    enqueued = {}

    async def fake_enqueue(tenant_id):
        enqueued["tenant_id"] = tenant_id

    monkeypatch.setattr(mo, "enqueue_provision_tenant", fake_enqueue)

    invite = await create_invite(session, created_by_account_id=None)
    state = _FakeState({"invite_id": invite.id, "slug": "acme", "display_name": "Acme", "default_lang": "ru"})
    query = AsyncMock()
    query.from_user = SimpleNamespace(id=555)
    query.message = SimpleNamespace(chat=SimpleNamespace(id=555), answer=AsyncMock())

    await mo.on_confirm(query, OwnerOnboardCb(action="confirm"), state, chat_id=555)

    from sqlmodel import select
    result = await session.execute(select(Tenant).where(Tenant.slug == "acme"))
    tenant = result.scalar_one()
    assert tenant.status == "provisioning"
    assert enqueued["tenant_id"] == tenant.id
    assert state.state == mo.ManualToken.awaiting
    assert (await state.get_data())["tenant_id"] == tenant.id


async def test_cancel_clears_state(monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    state = _FakeState({"slug": "x"})
    query = AsyncMock()
    query.message = SimpleNamespace(answer=AsyncMock())
    await mo.on_cancel(query, OwnerOnboardCb(action="cancel"), state)
    assert state.state is None
    assert await state.get_data() == {}


async def test_manual_token_finalizes(session, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)

    async def fake_validate(token):
        return (900, "zen_bot")

    monkeypatch.setattr(mo, "validate_bot_token", fake_validate)

    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="900:newtoken", answer=AsyncMock())

    await mo.on_manual_token(message, state)

    await session.refresh(tenant)
    assert tenant.status == "active"
    assert state.state is None  # cleared


async def test_manual_token_rejects_invalid(session, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)

    async def fake_validate(token):
        return None

    monkeypatch.setattr(mo, "validate_bot_token", fake_validate)

    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="bad", display_name="Bad",
        default_lang="ru", owner_tg_id=1, owner_chat_id=1,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="garbage", answer=AsyncMock())

    await mo.on_manual_token(message, state)

    await session.refresh(tenant)
    assert tenant.status != "active"  # still awaiting
    assert state.state is None or state.state == mo.ManualToken.awaiting
    message.answer.assert_awaited()
