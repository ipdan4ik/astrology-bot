from types import SimpleNamespace

from quantuum.auth.identity import find_or_create_account_by_tg

from .conftest import build_translator


class FakeMessage:
    def __init__(self, user_id):
        self.from_user = SimpleNamespace(id=user_id, language_code=None)
        self.chat = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def _patch_sessionmaker(monkeypatch, session):
    from quantuum.bot.middleware import account as mw

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(mw, "get_sessionmaker", lambda: _Maker())


async def test_disabled_account_is_blocked(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware.account import AccountMiddleware

    await build_translator(session, default_tenant.id)  # seed strings + langs
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="555")
    acc.status = "disabled"
    acc.ban_reason = "spam"
    session.add(acc)
    await session.commit()
    _patch_sessionmaker(monkeypatch, session)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = FakeMessage(555)
    await AccountMiddleware()(handler, event, {"tenant_id": default_tenant.id})

    assert called is False
    assert any("spam" in t for t in event.answers)


async def test_active_account_passes_through(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware.account import AccountMiddleware

    await build_translator(session, default_tenant.id)
    await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="556")
    await session.commit()
    _patch_sessionmaker(monkeypatch, session)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = FakeMessage(556)
    await AccountMiddleware()(handler, event, {"tenant_id": default_tenant.id})
    assert called is True
