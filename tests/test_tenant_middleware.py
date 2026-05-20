from types import SimpleNamespace

from quantuum.bot.middleware.tenant import TenantMiddleware
from quantuum.db.models import TenantBot


async def test_tenant_middleware_resolves_from_bot(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware import tenant as tenant_mod

    session.add(TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=555, bot_token_enc=b"e",
        webhook_secret_path="w555",
    ))
    await session.commit()

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(tenant_mod, "get_sessionmaker", lambda: _Maker())

    captured = {}

    async def handler(event, data):
        captured["tenant_id"] = data.get("tenant_id")
        return "ok"

    mw = TenantMiddleware()
    bot = SimpleNamespace(id=555)
    assert await mw(handler, SimpleNamespace(from_user=SimpleNamespace(id=1)), {"bot": bot}) == "ok"
    assert captured["tenant_id"] == default_tenant.id


async def test_tenant_middleware_unknown_bot_sets_none(session, monkeypatch):
    from types import SimpleNamespace

    from quantuum.bot.middleware import tenant as tenant_mod

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(tenant_mod, "get_sessionmaker", lambda: _Maker())
    captured = {}

    async def handler(event, data):
        captured["tenant_id"] = data.get("tenant_id")
        return "ok"

    mw = TenantMiddleware()
    bot = SimpleNamespace(id=987654)  # no tenant_bots row
    await mw(handler, SimpleNamespace(from_user=SimpleNamespace(id=1)), {"bot": bot})
    assert captured["tenant_id"] is None
