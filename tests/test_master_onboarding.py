from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.bot.handlers.master_onboarding import slug_is_available

from .conftest import build_translator


async def test_slug_is_available(session, default_tenant):
    assert await slug_is_available(session, "brand-new") is True
    assert await slug_is_available(session, "default") is False


async def test_master_cancel_kb_uses_owner_callback(session, default_tenant):
    from quantuum.bot.handlers.master_onboarding import master_cancel_kb
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    i18n = await build_translator(session, default_tenant.id)
    kb = await master_cancel_kb(i18n)
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


async def test_confirm_creates_tenant_and_enqueues(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb
    from quantuum.db.models import Tenant
    from quantuum.domain.invites import create_invite

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)
    enqueued = {}

    async def fake_enqueue(tenant_id):
        enqueued["tenant_id"] = tenant_id

    monkeypatch.setattr(mo, "enqueue_provision_tenant", fake_enqueue)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()  # create_invite now flushes; commit so a fresh session would see it
    state = _FakeState({"invite_id": invite.id, "slug": "acme", "display_name": "Acme", "default_lang": "ru"})
    query = AsyncMock()
    query.from_user = SimpleNamespace(id=555)
    query.message = SimpleNamespace(chat=SimpleNamespace(id=555), answer=AsyncMock())

    await mo.on_confirm(query, OwnerOnboardCb(action="confirm"), state, i18n=i18n, chat_id=555)

    from sqlmodel import select
    result = await session.execute(select(Tenant).where(Tenant.slug == "acme"))
    tenant = result.scalar_one()
    assert tenant.status == "provisioning"
    assert enqueued["tenant_id"] == tenant.id
    assert state.state == mo.ManualToken.awaiting
    assert (await state.get_data())["tenant_id"] == tenant.id


async def test_cancel_clears_state(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({"slug": "x"})
    query = AsyncMock()
    query.message = SimpleNamespace(answer=AsyncMock())
    await mo.on_cancel(query, OwnerOnboardCb(action="cancel"), state, i18n=i18n)
    assert state.state is None
    assert await state.get_data() == {}


async def test_manual_token_finalizes(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)

    async def fake_validate(token):
        return (900, "zen_bot")

    monkeypatch.setattr(mo, "validate_bot_token", fake_validate)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()  # create_invite now flushes; commit so a fresh session would see it
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="900:newtoken", answer=AsyncMock())

    await mo.on_manual_token(message, state, i18n=i18n)

    await session.refresh(tenant)
    assert tenant.status == "active"
    assert state.state is None  # cleared


async def test_manual_token_rejects_invalid(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)

    async def fake_validate(token):
        return None

    monkeypatch.setattr(mo, "validate_bot_token", fake_validate)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()  # create_invite now flushes; commit so a fresh session would see it
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="bad", display_name="Bad",
        default_lang="ru", owner_tg_id=1, owner_chat_id=1,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="garbage", answer=AsyncMock())

    await mo.on_manual_token(message, state, i18n=i18n)

    await session.refresh(tenant)
    assert tenant.status != "active"  # still awaiting
    assert state.state is None or state.state == mo.ManualToken.awaiting


async def test_managed_bot_created_finalizes(session, default_tenant, monkeypatch):
    from sqlmodel import select

    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.db.models import TenantBot
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})

    created = SimpleNamespace(bot_user=SimpleNamespace(id=900, username="zen_managed_bot"))
    message = SimpleNamespace(managed_bot_created=created, answer=AsyncMock())
    # bot(GetManagedBotToken(...)) -> token string
    bot = AsyncMock(return_value="900:managedtoken")

    await mo.on_managed_bot_created(message, state, i18n=i18n, bot=bot)

    await session.refresh(tenant)
    assert tenant.status == "active"
    assert state.state is None  # cleared
    bot.assert_awaited_once()  # GetManagedBotToken was called

    tb = (
        await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant.id))
    ).scalar_one()
    assert tb.bot_telegram_id == 900
    assert tb.bot_username == "zen_managed_bot"
    assert tb.status == "active"


async def test_slug_prompt_carries_cancel_keyboard(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    message = SimpleNamespace(text="acmebot", answer=AsyncMock())

    await mo.on_slug(message, state, i18n=i18n)

    assert state.state == mo.OwnerOnboarding.display_name
    _, kwargs = message.answer.await_args
    markup = kwargs.get("reply_markup")
    assert markup is not None
    cb = markup.inline_keyboard[0][0].callback_data
    assert OwnerOnboardCb.unpack(cb).action == "cancel"


async def test_display_name_prompt_carries_cancel_keyboard(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({"slug": "acme"})
    message = SimpleNamespace(text="Acme Co", answer=AsyncMock())

    await mo.on_display_name(message, state, i18n=i18n)

    assert state.state == mo.OwnerOnboarding.default_lang
    _, kwargs = message.answer.await_args
    markup = kwargs.get("reply_markup")
    assert markup is not None
    cb = markup.inline_keyboard[0][0].callback_data
    assert OwnerOnboardCb.unpack(cb).action == "cancel"


async def test_default_lang_renders_confirm(session, default_tenant, monkeypatch):
    """Regression: the confirm summary must render. The template uses {language}, not
    {lang} — passing lang= as a format var collides with the Translator's reserved
    `lang` and raised 't() got multiple values for argument lang'."""
    from quantuum.bot.handlers import master_onboarding as mo

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({"slug": "acme", "display_name": "Acme"})
    message = SimpleNamespace(text="ru", answer=AsyncMock())

    await mo.on_default_lang(message, state, i18n=i18n)

    assert state.state == mo.OwnerOnboarding.confirm
    text = message.answer.await_args.args[0]
    assert "acme" in text and "Acme" in text and "ru" in text  # rendered, no crash
    message.answer.assert_awaited()


async def test_finalize_publishes_bot_reload(session, default_tenant, monkeypatch):
    """After a managed bot is created and provisioning is finalized, the worker is nudged
    to reconcile so the new bot serves without a restart."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)

    published = AsyncMock()
    monkeypatch.setattr(mo, "publish_bot_reload", published)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    created = SimpleNamespace(bot_user=SimpleNamespace(id=900, username="zen_managed_bot"))
    message = SimpleNamespace(managed_bot_created=created, answer=AsyncMock())
    bot = AsyncMock(return_value="900:managedtoken")

    await mo.on_managed_bot_created(message, state, i18n=i18n, bot=bot)

    published.assert_awaited_once()


async def test_manual_token_rejects_bot_already_in_use(session, default_tenant, monkeypatch):
    """If the pasted token's bot id is already an active TenantBot for another tenant,
    finalize raises BotAlreadyInUseError; the handler shows token_in_use and the tenant
    stays provisioning so the owner can paste a different token."""
    from sqlmodel import select

    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.db.models import Tenant, TenantBot
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)

    # An existing active tenant already owns bot id 600002.
    taken = Tenant(slug="alreadytaken", display_name="Taken", status="active",
                   owner_tg_id="800", owner_chat_id="800")
    session.add(taken)
    await session.flush()
    session.add(TenantBot(
        tenant_id=taken.id, bot_token_enc=b"x", transport="polling",
        webhook_secret_path="taken-secret", status="active", bot_telegram_id=600002,
    ))
    await session.commit()

    monkeypatch.setattr(mo, "validate_bot_token", AsyncMock(return_value=(600002, "dupe_bot")))
    published = AsyncMock()
    monkeypatch.setattr(mo, "publish_bot_reload", published)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="claimer", display_name="Claimer",
        default_lang="ru", owner_tg_id=801, owner_chat_id=801,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="600002:dupetoken", answer=AsyncMock())

    await mo.on_manual_token(message, state, i18n=i18n)

    expected = await i18n("master.onboard.token_in_use")
    message.answer.assert_awaited_once_with(expected)
    published.assert_not_awaited()

    await session.refresh(tenant)
    assert tenant.status == "provisioning"  # not activated
    # FSM left awaiting so the owner can paste a different token
    assert state.state == mo.ManualToken.awaiting or state.state is None


async def test_manual_token_publishes_bot_reload(session, default_tenant, monkeypatch):
    """The pasted-token completion path also nudges the workers to hot-reload."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)
    monkeypatch.setattr(mo, "validate_bot_token", AsyncMock(return_value=(901, "manual_bot")))
    published = AsyncMock()
    monkeypatch.setattr(mo, "publish_bot_reload", published)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="man", display_name="Man",
        default_lang="ru", owner_tg_id=778, owner_chat_id=778,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="901:manualtoken", answer=AsyncMock())

    await mo.on_manual_token(message, state, i18n=i18n)

    published.assert_awaited_once()
