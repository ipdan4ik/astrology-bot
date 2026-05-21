from types import SimpleNamespace

from quantuum.bot.middleware.account import AccountMiddleware
from quantuum.db.models import PlatformString, TenantLanguage
from quantuum.i18n import Translator


def _patch_sessionmaker(monkeypatch, session):
    """Force AccountMiddleware to use the test session."""
    from quantuum.bot.middleware import account as account_mod

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    class _Maker:
        def __call__(self):
            return _Ctx()

    monkeypatch.setattr(account_mod, "get_sessionmaker", lambda: _Maker())


async def _seed_lang(session, tenant_id, *, default_lang: str = "en"):
    session.add(
        TenantLanguage(
            tenant_id=tenant_id, lang=default_lang, enabled=True, is_default=True
        )
    )
    session.add(PlatformString(key="greet", lang=default_lang, text="Hello"))
    await session.commit()


async def test_middleware_injects_translator_and_lang(
    session, default_tenant, monkeypatch
):
    _patch_sessionmaker(monkeypatch, session)
    await _seed_lang(session, default_tenant.id, default_lang="en")

    captured = {}

    async def handler(event, data):
        captured["data"] = data
        return "ok"

    mw = AccountMiddleware()
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=12345, language_code="de"),
        chat=SimpleNamespace(id=999),
    )
    result = await mw(handler, event, {"tenant_id": default_tenant.id})

    assert result == "ok"
    data = captured["data"]
    # Translator injected and ready
    assert isinstance(data["i18n"], Translator)
    # Resolved lang present (de not enabled → falls back to default "en")
    assert data["lang"] == "en"
    assert data["i18n"].lang == "en"
    # Existing keys preserved
    assert data["account"].tenant_id == default_tenant.id
    assert data["chat_id"] == 999


async def test_middleware_prefers_enabled_tg_language(
    session, default_tenant, monkeypatch
):
    _patch_sessionmaker(monkeypatch, session)
    await _seed_lang(session, default_tenant.id, default_lang="en")
    # Enable German too so the from_user.language_code is honoured.
    session.add(
        TenantLanguage(
            tenant_id=default_tenant.id, lang="de", enabled=True, is_default=False
        )
    )
    await session.commit()

    captured = {}

    async def handler(event, data):
        captured["data"] = data
        return "ok"

    mw = AccountMiddleware()
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=22222, language_code="de"),
        chat=SimpleNamespace(id=777),
    )
    await mw(handler, event, {"tenant_id": default_tenant.id})

    data = captured["data"]
    assert data["lang"] == "de"
    assert data["i18n"].lang == "de"


async def test_middleware_passthrough_does_not_inject_i18n(session, monkeypatch):
    _patch_sessionmaker(monkeypatch, session)
    captured = {}

    async def handler(event, data):
        captured["data"] = dict(data)
        return "ok"

    mw = AccountMiddleware()
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=1, language_code="en"),
        chat=SimpleNamespace(id=9),
    )
    result = await mw(handler, event, {"tenant_id": None})

    assert result == "ok"
    assert "i18n" not in captured["data"]
    assert "lang" not in captured["data"]
