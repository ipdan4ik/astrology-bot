from types import SimpleNamespace

from quantuum.bot.middleware.account import AccountMiddleware


async def test_account_middleware_injects_account(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware import account as account_mod

    # Force the middleware to use our test session + tenant.
    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        def __init__(self, _session=None):
            pass

        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(account_mod, "get_sessionmaker", lambda: _Maker())

    captured = {}

    async def handler(event, data):
        captured["account"] = data["account"]
        captured["chat_id"] = data["chat_id"]
        return "ok"

    mw = AccountMiddleware()
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        chat=SimpleNamespace(id=999),
    )
    result = await mw(handler, event, {"tenant_id": default_tenant.id})
    assert result == "ok"
    assert captured["account"].tenant_id == default_tenant.id
    assert captured["chat_id"] == 999
