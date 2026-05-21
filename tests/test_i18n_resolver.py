import pytest

from quantuum.db.models import PlatformString, TenantLanguage, TenantStringOverride
from quantuum.i18n.resolver import safe_format, t


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed(session, tid, *, default_lang: str = "en"):
    """Seed a minimal set of platform strings, overrides, and a default language."""
    # Platform strings for English
    session.add(PlatformString(key="greet", lang="en", text="Hello {name}"))
    session.add(PlatformString(key="bye", lang="en", text="Goodbye"))
    # Platform string only in German (for default-lang fallback test)
    session.add(PlatformString(key="only_de", lang="de", text="Nur Deutsch"))
    # Tenant override for English
    session.add(
        TenantStringOverride(tenant_id=tid, key="greet", lang="en", text="Hey {name}")
    )
    # Tenant default language
    session.add(
        TenantLanguage(tenant_id=tid, lang=default_lang, enabled=True, is_default=True)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# safe_format
# ---------------------------------------------------------------------------


def test_safe_format_fills_var():
    assert safe_format("Hi {name}", {"name": "A"}) == "Hi A"


def test_safe_format_leaves_missing_var_intact():
    assert safe_format("Hi {name}", {}) == "Hi {name}"


def test_safe_format_multiple_vars():
    assert safe_format("{a} and {b}", {"a": "X"}) == "X and {b}"


# ---------------------------------------------------------------------------
# t() — 6-step fallback chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t_override_hit(session, default_tenant):
    """Tenant override for (key, lang) wins over platform string."""
    await _seed(session, default_tenant.id)
    result = await t(session, "greet", "en", tenant_id=default_tenant.id, name="Alice")
    assert result == "Hey Alice"


@pytest.mark.asyncio
async def test_t_platform_hit(session, default_tenant):
    """No override → platform string for lang is returned."""
    await _seed(session, default_tenant.id)
    result = await t(session, "bye", "en", tenant_id=default_tenant.id)
    assert result == "Goodbye"


@pytest.mark.asyncio
async def test_t_default_lang_fallback(session, default_tenant):
    """Key absent in requested lang but present in tenant default lang → returns default-lang text."""
    # Seed with German as the tenant default
    session.add(PlatformString(key="only_de", lang="de", text="Nur Deutsch"))
    session.add(
        TenantLanguage(
            tenant_id=default_tenant.id, lang="de", enabled=True, is_default=True
        )
    )
    await session.commit()

    # Request French — key absent in 'fr', but present in default 'de'
    result = await t(session, "only_de", "fr", tenant_id=default_tenant.id)
    assert result == "Nur Deutsch"


@pytest.mark.asyncio
async def test_t_arg_default(session, default_tenant):
    """Key absent everywhere → returns the default= arg, formatted."""
    await _seed(session, default_tenant.id)
    result = await t(
        session,
        "nonexistent",
        "en",
        tenant_id=default_tenant.id,
        default="Fallback {x}",
        x="val",
    )
    assert result == "Fallback val"


@pytest.mark.asyncio
async def test_t_missing_sentinel(session, default_tenant):
    """Key absent and no default → returns [missing: key] sentinel."""
    await _seed(session, default_tenant.id)
    result = await t(session, "nonexistent", "en", tenant_id=default_tenant.id)
    assert result == "[missing: nonexistent]"


@pytest.mark.asyncio
async def test_t_safe_format_in_result(session, default_tenant):
    """Template with unfilled var is left intact (safe_format behaviour via t())."""
    await _seed(session, default_tenant.id)
    # 'greet' override is "Hey {name}" — call without providing `name`
    result = await t(session, "greet", "en", tenant_id=default_tenant.id)
    assert result == "Hey {name}"
