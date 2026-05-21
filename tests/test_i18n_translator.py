import pytest

from quantuum.db.models import PlatformString, TenantLanguage
from quantuum.i18n.resolver import Translator, resolve_lang


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed(session, tenant_id: int) -> None:
    """Seed two enabled languages (ru default, en non-default) and two greet strings."""
    session.add(TenantLanguage(tenant_id=tenant_id, lang="ru", enabled=True, is_default=True))
    session.add(TenantLanguage(tenant_id=tenant_id, lang="en", enabled=True, is_default=False))
    session.add(PlatformString(key="greet", lang="ru", text="Привет"))
    session.add(PlatformString(key="greet", lang="en", text="Hello"))
    await session.commit()


# ---------------------------------------------------------------------------
# resolve_lang
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_lang_prefers_enabled_preferred(session, default_tenant):
    """preferred_lang="en" (enabled) → returns "en" immediately."""
    await _seed(session, default_tenant.id)
    result = await resolve_lang(
        session,
        tenant_id=default_tenant.id,
        preferred_lang="en",
        tg_language_code=None,
    )
    assert result == "en"


@pytest.mark.asyncio
async def test_resolve_lang_falls_to_tg_then_default(session, default_tenant):
    """preferred=None, tg="en" → "en"; preferred=None, tg=None → "ru" (default)."""
    await _seed(session, default_tenant.id)

    result_tg = await resolve_lang(
        session,
        tenant_id=default_tenant.id,
        preferred_lang=None,
        tg_language_code="en",
    )
    assert result_tg == "en"

    result_none = await resolve_lang(
        session,
        tenant_id=default_tenant.id,
        preferred_lang=None,
        tg_language_code=None,
    )
    assert result_none == "ru"


@pytest.mark.asyncio
async def test_resolve_lang_ignores_disabled_preferred(session, default_tenant):
    """preferred_lang="de" (not enabled) → falls through to default "ru"."""
    await _seed(session, default_tenant.id)
    result = await resolve_lang(
        session,
        tenant_id=default_tenant.id,
        preferred_lang="de",
        tg_language_code=None,
    )
    assert result == "ru"


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translator_build_and_call(session, default_tenant):
    """Translator.build resolves lang; __call__ returns the correct translation."""
    await _seed(session, default_tenant.id)

    tr = await Translator.build(
        session,
        tenant_id=default_tenant.id,
        preferred_lang="en",
        tg_language_code=None,
    )
    assert tr.lang == "en"
    result = await tr("greet")
    assert result == "Hello"
