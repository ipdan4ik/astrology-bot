"""Tests for tenant i18n admin routes:
  GET/PUT  /admin/tenants/{tenant_id}/languages
  GET/PUT/DELETE /admin/tenants/{tenant_id}/strings[/{key}/{lang}]
  GET/PUT  /admin/tenants/{tenant_id}/config
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import (
    Account,
    AuditLog,
    PlatformString,
)
from quantuum.domain.tenants import grant_role
from quantuum.i18n.resolver import t


# ---------------------------------------------------------------------------
# Fixtures (mirror test_api_admin_tenants.py helpers)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_role_headers(session, tenant_id: int, role: str) -> dict:
    """Create an account in the tenant, grant role, return auth headers."""
    acc = Account(tenant_id=tenant_id, is_superadmin=False)
    session.add(acc)
    await session.flush()
    await grant_role(
        session,
        tenant_id=tenant_id,
        account_id=acc.id,
        role=role,
        granted_by_account_id=None,
    )
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, tenant_id, False)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def owner_headers(session, default_tenant):
    return await _make_role_headers(session, default_tenant.id, "owner")


@pytest_asyncio.fixture
async def admin_headers(session, default_tenant):
    return await _make_role_headers(session, default_tenant.id, "admin")


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    """A regular customer in the tenant with no owner/admin role."""
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Task 7 — Languages
# ---------------------------------------------------------------------------


async def test_put_languages_owner_200(client, owner_headers, default_tenant, session):
    """Owner can PUT a full language set with exactly one default."""
    payload = {
        "languages": [
            {"lang": "ru", "enabled": True, "is_default": True},
            {"lang": "en", "enabled": True, "is_default": False},
        ]
    }
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json=payload,
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    langs = {item["lang"]: item for item in body}
    assert "ru" in langs
    assert "en" in langs
    assert langs["ru"]["is_default"] is True
    assert langs["en"]["is_default"] is False
    assert langs["ru"]["enabled"] is True
    assert langs["en"]["enabled"] is True


async def test_get_languages_returns_list(client, owner_headers, default_tenant, session):
    """After PUT, GET returns the same set."""
    payload = {
        "languages": [
            {"lang": "ru", "enabled": True, "is_default": True},
            {"lang": "en", "enabled": True, "is_default": False},
        ]
    }
    await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json=payload,
        headers=owner_headers,
    )

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/languages",
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    langs = {item["lang"] for item in body}
    assert "ru" in langs
    assert "en" in langs


async def test_put_languages_zero_defaults_400(
    client, owner_headers, default_tenant
):
    """PUT with zero is_default=True items must return 400."""
    payload = {
        "languages": [
            {"lang": "ru", "enabled": True, "is_default": False},
            {"lang": "en", "enabled": True, "is_default": False},
        ]
    }
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json=payload,
        headers=owner_headers,
    )
    assert r.status_code == 400


async def test_put_languages_two_defaults_400(
    client, owner_headers, default_tenant
):
    """PUT with two is_default=True items must return 400."""
    payload = {
        "languages": [
            {"lang": "ru", "enabled": True, "is_default": True},
            {"lang": "en", "enabled": True, "is_default": True},
        ]
    }
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json=payload,
        headers=owner_headers,
    )
    assert r.status_code == 400


async def test_put_languages_customer_403(client, customer_headers, default_tenant):
    """Customer cannot PUT languages."""
    payload = {
        "languages": [
            {"lang": "en", "enabled": True, "is_default": True},
        ]
    }
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json=payload,
        headers=customer_headers,
    )
    assert r.status_code == 403


async def test_put_languages_switch_default_no_integrity_error(
    client, owner_headers, default_tenant, session
):
    """Switching the default language does not raise a UniqueConstraint/IntegrityError."""
    # First PUT: ru is default
    r1 = await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json={
            "languages": [
                {"lang": "ru", "enabled": True, "is_default": True},
                {"lang": "en", "enabled": True, "is_default": False},
            ]
        },
        headers=owner_headers,
    )
    assert r1.status_code == 200

    # Second PUT: switch default to en — must not raise IntegrityError
    r2 = await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json={
            "languages": [
                {"lang": "ru", "enabled": True, "is_default": False},
                {"lang": "en", "enabled": True, "is_default": True},
            ]
        },
        headers=owner_headers,
    )
    assert r2.status_code == 200
    langs = {item["lang"]: item for item in r2.json()}
    assert langs["en"]["is_default"] is True
    assert langs["ru"]["is_default"] is False


async def test_put_languages_creates_audit(
    client, owner_headers, default_tenant, session
):
    """PUT languages writes an audit log row."""
    await client.put(
        f"/admin/tenants/{default_tenant.id}/languages",
        json={
            "languages": [
                {"lang": "en", "enabled": True, "is_default": True},
            ]
        },
        headers=owner_headers,
    )
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "languages.update",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Task 8 — String overrides
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_platform_string(session, default_tenant):
    """Seed PlatformString key='greet', lang='en', text='Hi'."""
    ps = PlatformString(key="greet", lang="en", text="Hi")
    session.add(ps)
    await session.commit()
    return ps


async def test_get_strings_no_override(
    client, owner_headers, default_tenant, seeded_platform_string
):
    """GET strings?lang=en shows platform string with is_override=False."""
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/strings?lang=en",
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    greet = next((s for s in body if s["key"] == "greet"), None)
    assert greet is not None
    assert greet["text"] == "Hi"
    assert greet["is_override"] is False


async def test_put_string_override_persists(
    client, owner_headers, default_tenant, seeded_platform_string
):
    """PUT an override sets text='Yo' for key='greet' lang='en'."""
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/strings",
        json={"key": "greet", "lang": "en", "text": "Yo"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "greet"
    assert body["lang"] == "en"
    assert body["text"] == "Yo"
    assert body["is_override"] is True


async def test_get_strings_after_override_shows_override(
    client, owner_headers, default_tenant, seeded_platform_string
):
    """After PUT override, GET strings returns is_override=True and the new text."""
    await client.put(
        f"/admin/tenants/{default_tenant.id}/strings",
        json={"key": "greet", "lang": "en", "text": "Yo"},
        headers=owner_headers,
    )
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/strings?lang=en",
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    greet = next(s for s in body if s["key"] == "greet")
    assert greet["text"] == "Yo"
    assert greet["is_override"] is True


async def test_put_string_override_invalidates_cache_resolver(
    client, owner_headers, default_tenant, seeded_platform_string, session
):
    """After PUT override, the i18n resolver returns the new text (cache was invalidated)."""
    # Warm the cache by resolving before the override
    pre = await t(session, "greet", "en", tenant_id=default_tenant.id)
    assert pre == "Hi"

    # PUT the override via API
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/strings",
        json={"key": "greet", "lang": "en", "text": "Yo"},
        headers=owner_headers,
    )
    assert r.status_code == 200

    # Resolver must now return the overridden value (cache invalidated)
    post = await t(session, "greet", "en", tenant_id=default_tenant.id)
    assert post == "Yo"


async def test_delete_string_override_resets_resolver(
    client, owner_headers, default_tenant, seeded_platform_string, session
):
    """DELETE the override → resolver returns the original platform string."""
    # Set the override
    await client.put(
        f"/admin/tenants/{default_tenant.id}/strings",
        json={"key": "greet", "lang": "en", "text": "Yo"},
        headers=owner_headers,
    )
    assert (await t(session, "greet", "en", tenant_id=default_tenant.id)) == "Yo"

    # Delete the override
    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/strings/greet/en",
        headers=owner_headers,
    )
    assert r.status_code in (200, 204)

    # Resolver must return the original platform string
    result = await t(session, "greet", "en", tenant_id=default_tenant.id)
    assert result == "Hi"


async def test_delete_string_override_missing_404(
    client, owner_headers, default_tenant
):
    """DELETE a non-existent override → 404."""
    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/strings/nonexistent/en",
        headers=owner_headers,
    )
    assert r.status_code == 404


async def test_put_string_creates_audit(
    client, owner_headers, default_tenant, seeded_platform_string, session
):
    """PUT string override writes an audit row with key and lang in payload."""
    await client.put(
        f"/admin/tenants/{default_tenant.id}/strings",
        json={"key": "greet", "lang": "en", "text": "Yo"},
        headers=owner_headers,
    )
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "string.override",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.payload_jsonb["key"] == "greet"
    assert log.payload_jsonb["lang"] == "en"


async def test_delete_string_creates_audit(
    client, owner_headers, default_tenant, seeded_platform_string, session
):
    """DELETE string override writes an audit row."""
    # First create the override
    await client.put(
        f"/admin/tenants/{default_tenant.id}/strings",
        json={"key": "greet", "lang": "en", "text": "Yo"},
        headers=owner_headers,
    )
    await client.delete(
        f"/admin/tenants/{default_tenant.id}/strings/greet/en",
        headers=owner_headers,
    )
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "string.revert",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_get_strings_customer_403(
    client, customer_headers, default_tenant, seeded_platform_string
):
    """Customer cannot GET strings."""
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/strings?lang=en",
        headers=customer_headers,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Task 9 — Config
# ---------------------------------------------------------------------------


async def test_put_config_owner_200(client, owner_headers, default_tenant):
    """Owner can PUT a config key → returns {key, value}."""
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/config",
        json={"key": "welcome", "value": {"x": 1}},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "welcome"
    assert body["value"] == {"x": 1}


async def test_get_config_returns_dict(client, owner_headers, default_tenant):
    """GET config returns a dict containing previously PUT keys."""
    await client.put(
        f"/admin/tenants/{default_tenant.id}/config",
        json={"key": "welcome", "value": {"x": 1}},
        headers=owner_headers,
    )
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/config",
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "welcome" in body
    assert body["welcome"] == {"x": 1}


async def test_put_config_upsert(client, owner_headers, default_tenant):
    """Repeated PUT on same key updates the value."""
    await client.put(
        f"/admin/tenants/{default_tenant.id}/config",
        json={"key": "welcome", "value": {"x": 1}},
        headers=owner_headers,
    )
    r = await client.put(
        f"/admin/tenants/{default_tenant.id}/config",
        json={"key": "welcome", "value": {"x": 99}},
        headers=owner_headers,
    )
    assert r.status_code == 200
    assert r.json()["value"] == {"x": 99}


async def test_put_config_creates_audit(
    client, owner_headers, default_tenant, session
):
    """PUT config writes an audit row."""
    await client.put(
        f"/admin/tenants/{default_tenant.id}/config",
        json={"key": "welcome", "value": {"x": 1}},
        headers=owner_headers,
    )
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "config.update",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_get_config_admin_200(client, admin_headers, default_tenant):
    """Admin can GET config."""
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/config",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


async def test_get_config_customer_403(client, customer_headers, default_tenant):
    """Customer cannot GET config."""
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/config",
        headers=customer_headers,
    )
    assert r.status_code == 403
