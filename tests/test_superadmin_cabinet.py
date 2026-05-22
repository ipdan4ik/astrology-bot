from types import SimpleNamespace

from sqlmodel import select

from quantuum.db.models import Account, AccountIdentity, AuditLog, Tenant, TenantBot

from .conftest import build_translator

SA_TG = 900900
PLAIN_TG = 111222


class FakeMessage:
    def __init__(self, *, from_user_id, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=from_user_id)
        self.chat = SimpleNamespace(id=from_user_id)
        self.answers = []  # (text, reply_markup)

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, *, from_user_id):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage(from_user_id=from_user_id)
        self.answers = []  # (text, kwargs)

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeState:
    def __init__(self, data=None):
        self._data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, s):
        self.state = s

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


def _inline(markup):
    return [b for row in markup.inline_keyboard for b in row]


async def _make_superadmin(session, tg=SA_TG):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=str(tg)))
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_admin_menu_for_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    i18n = await build_translator(session, default_tenant.id)

    msg = FakeMessage(from_user_id=SA_TG)
    await sa.on_admin(msg, i18n=i18n)

    text, markup = msg.answers[0]
    actions = {SuperAdminCb.unpack(b.callback_data).action for b in _inline(markup)}
    assert actions == {"tenants", "invites"}


async def test_admin_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa

    _patch_sessionmaker(monkeypatch, sa, session)
    i18n = await build_translator(session, default_tenant.id)

    msg = FakeMessage(from_user_id=PLAIN_TG)
    await sa.on_admin(msg, i18n=i18n)

    assert len(msg.answers) == 1
    text, markup = msg.answers[0]
    assert markup is None  # no menu
    assert "прав" in text or "authoriz" in text.lower()


async def _make_tenant_with_bot(session, *, slug, status="active"):
    t = Tenant(slug=slug, display_name=slug.upper(), status=status)
    session.add(t)
    await session.flush()
    bot = TenantBot(
        tenant_id=t.id, bot_token_enc=b"x", webhook_secret_path=f"wh-{slug}",
        status="paused" if status == "suspended" else "active",
    )
    session.add(bot)
    await session.commit()
    await session.refresh(t)
    await session.refresh(bot)
    return t, bot


async def _audit_rows(session, tenant_id, action):
    rows = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id, AuditLog.action == action)
    )
    return list(rows.scalars().all())


async def test_tenants_list_lists_tenants(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, _bot = await _make_tenant_with_bot(session, slug="acme")
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenants(q, SuperAdminCb(action="tenants"), i18n=i18n)

    _, markup = q.message.answers[0]
    cbs = [SuperAdminCb.unpack(b.callback_data) for b in _inline(markup)]
    tenant_ids = {cb.tenant_id for cb in cbs if cb.action == "tenant"}
    assert t.id in tenant_ids


async def test_tenant_suspend_then_resume(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, bot = await _make_tenant_with_bot(session, slug="beta")
    i18n = await build_translator(session, default_tenant.id)

    q1 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_suspend(q1, SuperAdminCb(action="suspend", tenant_id=t.id), i18n=i18n)
    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "suspended"
    assert bot.status == "paused"
    assert len(await _audit_rows(session, t.id, "tenant.pause")) == 1

    q2 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_resume(q2, SuperAdminCb(action="resume", tenant_id=t.id), i18n=i18n)
    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"
    assert bot.status == "active"
    assert len(await _audit_rows(session, t.id, "tenant.resume")) == 1


async def test_tenant_suspend_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    t, _bot = await _make_tenant_with_bot(session, slug="gamma")
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=PLAIN_TG)  # not a superadmin
    await sa.on_tenant_suspend(q, SuperAdminCb(action="suspend", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # unchanged
    assert await _audit_rows(session, t.id, "tenant.pause") == []
    assert q.answers and q.answers[-1][1].get("show_alert") is True


async def test_delete_flow_success(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, bot = await _make_tenant_with_bot(session, slug="delme")
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)
    assert state.state == sa.SuperAdminDelete.awaiting_confirm
    assert (await state.get_data())["slug"] == t.slug

    msg = FakeMessage(from_user_id=SA_TG, text=t.slug)
    await sa.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "archived"
    assert t.slug.endswith(f"__del{t.id}")
    assert bot.status == "archived"
    assert len(await _audit_rows(session, t.id, "tenant.delete")) == 1
    assert state.state is None


async def test_delete_slug_mismatch_keeps_tenant(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, _bot = await _make_tenant_with_bot(session, slug="keepme")
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    msg = FakeMessage(from_user_id=SA_TG, text="WRONG")
    await sa.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"
    assert await _audit_rows(session, t.id, "tenant.delete") == []
    assert state.state == sa.SuperAdminDelete.awaiting_confirm  # stays to retry


async def test_delete_cancel(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa

    _patch_sessionmaker(monkeypatch, sa, session)
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState({"tenant_id": 1, "slug": "x"})
    state.state = sa.SuperAdminDelete.awaiting_confirm

    msg = FakeMessage(from_user_id=SA_TG)
    await sa.on_delete_cancel(msg, state, i18n=i18n)

    assert state.state is None
    assert await state.get_data() == {}


async def test_delete_request_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    t, _bot = await _make_tenant_with_bot(session, slug="safe")
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=PLAIN_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    assert state.state is None
    assert q.answers and q.answers[-1][1].get("show_alert") is True


async def _make_platform_tenant(session):
    from quantuum.db.models import Tenant, TenantBot

    t = Tenant(slug="platform", display_name="Platform", is_platform=True, status="active")
    session.add(t)
    await session.flush()
    bot = TenantBot(tenant_id=t.id, bot_token_enc=b"x", webhook_secret_path="wh-platform", status="active")
    session.add(bot)
    await session.commit()
    await session.refresh(t)
    await session.refresh(bot)
    return t, bot


async def test_suspend_platform_tenant_blocked(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, bot = await _make_platform_tenant(session)
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_suspend(q, SuperAdminCb(action="suspend", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"  # unchanged
    assert bot.status == "active"
    assert await _audit_rows(session, t.id, "tenant.pause") == []
    assert q.answers and q.answers[-1][1].get("show_alert") is True


async def test_delete_platform_tenant_blocked(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, _bot = await _make_platform_tenant(session)
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # NOT archived
    assert state.state is None  # FSM not entered
    assert q.answers and q.answers[-1][1].get("show_alert") is True


async def test_new_invite_returns_deeplink(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb
    from quantuum.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MASTER_BOT_USERNAME", "quantuum_master_bot")
    get_settings.cache_clear()

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_new_invite(q, SuperAdminCb(action="newinvite"), i18n=i18n)

    text = q.message.answers[0][0]
    assert "t.me/quantuum_master_bot?start=" in text
    get_settings.cache_clear()


async def test_invites_list_and_revoke(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb
    from quantuum.domain.invites import create_invite

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    inv = await create_invite(session, created_by_account_id=None)
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    # list shows the invite with a revoke button
    q1 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_invites(q1, SuperAdminCb(action="invites"), i18n=i18n)
    _, markup = q1.message.answers[0]
    revoke_ids = {
        SuperAdminCb.unpack(b.callback_data).invite_id
        for b in _inline(markup)
        if SuperAdminCb.unpack(b.callback_data).action == "revoke"
    }
    assert inv.id in revoke_ids

    # revoke it
    q2 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_revoke_invite(q2, SuperAdminCb(action="revoke", invite_id=inv.id), i18n=i18n)
    await session.refresh(inv)
    assert inv.status == "revoked"


async def test_new_invite_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=PLAIN_TG)
    await sa.on_new_invite(q, SuperAdminCb(action="newinvite"), i18n=i18n)

    assert q.answers and q.answers[-1][1].get("show_alert") is True
