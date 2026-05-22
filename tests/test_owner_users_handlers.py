from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import OwnerUserCb
from quantuum.db.models import Account, AccountIdentity
from quantuum.domain.accounts import set_account_ban
from quantuum.domain.tenants import grant_role

from .conftest import build_translator

TG = 222


class FakeMessage:
    def __init__(self, *, from_user_id=TG, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=from_user_id)
        self.answers = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, *, from_user_id=TG):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage(from_user_id=from_user_id)
        self.answers = []  # (text, show_alert)

    async def answer(self, text="", show_alert=False, **kwargs):
        self.answers.append((text, show_alert))


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


async def _owner(session, tenant):
    acc = Account(tenant_id=tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=str(TG)))
    await session.commit()
    await grant_role(session, tenant_id=tenant.id, account_id=acc.id, role="owner")
    await session.commit()
    return acc


async def test_list_renders_rows(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    query = FakeCallbackQuery()
    await ou.on_users_list(query, OwnerUserCb(action="list", tenant_id=default_tenant.id, page=0), i18n)

    header, markup = query.message.answers[0]
    assert "Quantuum" in header
    opens = [b for b in _inline(markup) if OwnerUserCb.unpack(b.callback_data).action == "open"]
    assert len(opens) >= 2  # owner + customer accounts


async def test_list_unauthorized(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    i18n = await build_translator(session, default_tenant.id)
    query = FakeCallbackQuery(from_user_id=999)  # no role
    await ou.on_users_list(query, OwnerUserCb(action="list", tenant_id=default_tenant.id, page=0), i18n)
    assert query.answers and query.answers[-1][1] is True  # show_alert no_rights
    assert query.message.answers == []


async def test_open_renders_card_with_ban(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await set_account_ban(session, target.id, reason="spam")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    query = FakeCallbackQuery()
    await ou.on_user_open(query, OwnerUserCb(action="open", tenant_id=default_tenant.id, account_id=target.id), i18n)
    text, markup = query.message.answers[0]
    assert "Telegram ID: 1000" in text
    assert "spam" in text
    labels = {b.text for b in _inline(markup)}
    assert "✅ Разбанить" in labels  # unban offered for a banned user


async def test_open_not_found(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    i18n = await build_translator(session, default_tenant.id)
    query = FakeCallbackQuery()
    await ou.on_user_open(query, OwnerUserCb(action="open", tenant_id=default_tenant.id, account_id=987654), i18n)
    assert query.answers[-1][1] is True  # not_found alert
    assert query.message.answers == []
