"""Handler-level tests for the owner-console master-bot commands (Plan 5c, Tasks 2+3).

The master bot identifies the owner by ``message.from_user.id`` across tenants.
We invoke the handlers with fake Message/CommandObject objects that capture the
``answer`` calls, and monkeypatch ``get_sessionmaker`` to return the test session.
Seeding mirrors tests/test_owner_console_domain.py.
"""
from types import SimpleNamespace

from quantuum.db.models import Account, AccountIdentity, Tenant
from quantuum.domain.tenants import grant_role

from .conftest import build_translator

TG = 222


class FakeMessage:
    def __init__(self, *, from_user_id=TG, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=from_user_id)
        self.answers = []  # list of (text, reply_markup)

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


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


async def _make_tenant(session, slug, display_name, status="active"):
    t = Tenant(slug=slug, display_name=display_name, status=status)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def _seed_account_with_role(session, *, tenant, role, tg=str(TG)):
    acc = Account(tenant_id=tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg))
    await session.commit()
    if role is not None:
        await grant_role(session, tenant_id=tenant.id, account_id=acc.id, role=role)
    return acc


# ── /tenants ─────────────────────────────────────────────────────────────────

async def test_tenants_lists_managed(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "alpha", "Alpha")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_tenants(msg, i18n=i18n)

    text = msg.answers[0][0]
    assert "alpha" in text
    assert "Alpha" in text


async def test_tenants_no_tenants(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    i18n = await build_translator(session, default_tenant.id)
    msg = FakeMessage(from_user_id=99999)
    await oc.on_tenants(msg, i18n=i18n)

    assert "нет тенантов" in msg.answers[0][0]


# ── /manage <slug> ───────────────────────────────────────────────────────────

async def test_manage_managed_tenant_active_shows_pause(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "beta", "Beta", status="active")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args="beta"), i18n=i18n)

    text, markup = msg.answers[0]
    assert "beta" in text
    buttons = [b for b in _inline(markup) if b.callback_data.startswith("omng:")]
    cbs = [OwnerManageCb.unpack(b.callback_data) for b in buttons]
    assert all(cb.tenant_id == t.id for cb in cbs)
    actions = {cb.action for cb in cbs}
    assert "stats" in actions
    assert "pause" in actions
    assert "transfer" in actions
    assert "resume" not in actions


async def test_manage_paused_tenant_shows_resume(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "gamma", "Gamma", status="suspended")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args="gamma"), i18n=i18n)

    _, markup = msg.answers[0]
    actions = {
        OwnerManageCb.unpack(b.callback_data).action
        for b in _inline(markup)
        if b.callback_data.startswith("omng:")
    }
    assert "resume" in actions
    assert "pause" not in actions


async def test_manage_unmanaged_slug(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    # Tenant exists but the user holds no role in it.
    t = await _make_tenant(session, "delta", "Delta")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args="delta"), i18n=i18n)

    assert "нет прав" in msg.answers[0][0]


async def test_manage_missing_args(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    i18n = await build_translator(session, default_tenant.id)
    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args=""), i18n=i18n)

    assert "Использование" in msg.answers[0][0]


class FakeCallbackMessage:
    def __init__(self, *, from_user_id):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.answers = []
        self.edits = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.edits.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, *, from_user_id):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeCallbackMessage(from_user_id=from_user_id)
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


async def test_manage_menu_has_no_back_row(session, monkeypatch):
    """The top-level manage menu must NOT carry a back-to-menu row."""
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "zeta", "Zeta", status="active")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args="zeta"), i18n=i18n)
    _, markup = msg.answers[0]
    actions = {
        OwnerManageCb.unpack(b.callback_data).action
        for b in _inline(markup)
        if b.callback_data.startswith("omng:")
    }
    assert "menu" not in actions


async def test_manage_menu_back_callback_rerenders(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "eta", "Eta", status="active")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    q = FakeCallbackQuery(from_user_id=TG)
    await oc.on_manage_menu(q, OwnerManageCb(action="menu", tenant_id=t.id), i18n=i18n)

    assert q.message.edits, "back callback should re-render the menu in place"
    text, markup = q.message.edits[0]
    assert t.slug in text
    actions = {
        OwnerManageCb.unpack(b.callback_data).action
        for b in _inline(markup)
        if b.callback_data.startswith("omng:")
    }
    assert "stats" in actions and "transfer" in actions


async def test_manage_menu_back_denied_for_non_owner(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "theta", "Theta", status="active")
    i18n = await build_translator(session, t.id)

    q = FakeCallbackQuery(from_user_id=98765)  # no role in t
    await oc.on_manage_menu(q, OwnerManageCb(action="menu", tenant_id=t.id), i18n=i18n)

    assert not q.message.edits
    assert q.answers and q.answers[-1][1].get("show_alert") is True


async def test_manage_shows_delete_button(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "epsilon", "Epsilon", status="active")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args="epsilon"), i18n=i18n)

    _, markup = msg.answers[0]
    actions = {
        OwnerManageCb.unpack(b.callback_data).action
        for b in _inline(markup)
        if b.callback_data.startswith("omng:")
    }
    assert "delete" in actions
