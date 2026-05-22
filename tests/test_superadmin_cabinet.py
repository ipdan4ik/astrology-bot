from types import SimpleNamespace

from quantuum.db.models import Account, AccountIdentity

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
