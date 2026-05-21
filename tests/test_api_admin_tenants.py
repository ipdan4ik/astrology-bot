"""Tests for /admin/tenants routes: GET, PATCH, pause, resume."""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import Account, AuditLog, Tenant, TenantBot
from quantuum.domain.tenants import grant_role


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def sa_headers(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, None, True)
    return {"Authorization": f"Bearer {token}"}


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


@pytest_asyncio.fixture
async def other_tenant_headers(session):
    """An owner in a *different* tenant — should be forbidden on default_tenant."""
    other = Tenant(slug="other-tenant", display_name="Other")
    session.add(other)
    await session.flush()
    headers = await _make_role_headers(session, other.id, "owner")
    await session.commit()
    return headers, other.id


# ---------------------------------------------------------------------------
# GET /{tenant_id}  — auth matrix
# ---------------------------------------------------------------------------


async def test_get_owner_200(client, owner_headers, default_tenant):
    r = await client.get(f"/admin/tenants/{default_tenant.id}", headers=owner_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == default_tenant.id
    assert body["slug"] == "default"
    assert "status" in body
    assert "tier" in body
    assert "is_platform" in body
    assert "primary_owner_account_id" in body
    assert "created_at" in body
    # bot field present (may be None since fixture doesn't create a bot)
    assert "bot" in body


async def test_get_admin_200(client, admin_headers, default_tenant):
    r = await client.get(f"/admin/tenants/{default_tenant.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["id"] == default_tenant.id


async def test_get_superadmin_200(client, sa_headers, default_tenant):
    r = await client.get(f"/admin/tenants/{default_tenant.id}", headers=sa_headers)
    assert r.status_code == 200
    assert r.json()["id"] == default_tenant.id


async def test_get_customer_403(client, customer_headers, default_tenant):
    r = await client.get(f"/admin/tenants/{default_tenant.id}", headers=customer_headers)
    assert r.status_code == 403


async def test_get_other_tenant_403(client, other_tenant_headers, default_tenant):
    headers, _other_id = other_tenant_headers
    r = await client.get(f"/admin/tenants/{default_tenant.id}", headers=headers)
    assert r.status_code == 403


async def test_get_missing_tenant_404(client, sa_headers):
    r = await client.get("/admin/tenants/999999", headers=sa_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /{tenant_id} — bot field populated
# ---------------------------------------------------------------------------


async def test_get_includes_bot(client, owner_headers, default_tenant, session):
    from quantuum.common.crypto import encrypt_token

    bot = TenantBot(
        tenant_id=default_tenant.id,
        bot_username="testbot",
        bot_token_enc=encrypt_token("123:testtoken"),
        webhook_secret_path="some-secret",
        status="active",
    )
    session.add(bot)
    await session.commit()

    r = await client.get(f"/admin/tenants/{default_tenant.id}", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["bot"] == {"username": "testbot", "status": "active"}


# ---------------------------------------------------------------------------
# PATCH /{tenant_id}
# ---------------------------------------------------------------------------


async def test_patch_display_name_200(client, owner_headers, default_tenant, session):
    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}",
        json={"display_name": "New Name"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "New Name"

    # Verify DB updated
    await session.refresh(default_tenant)
    assert default_tenant.display_name == "New Name"


async def test_patch_creates_audit_log(client, owner_headers, default_tenant, session):
    await client.patch(
        f"/admin/tenants/{default_tenant.id}",
        json={"display_name": "Audited Name"},
        headers=owner_headers,
    )

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "tenant.update",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.entity_type == "tenant"
    assert log.entity_id == str(default_tenant.id)
    assert "before" in log.payload_jsonb
    assert "after" in log.payload_jsonb


async def test_patch_tier_ignored_for_non_superadmin(client, owner_headers, default_tenant, session):
    old_tier = default_tenant.tier
    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}",
        json={"tier": "vip"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    assert r.json()["tier"] == old_tier  # unchanged

    await session.refresh(default_tenant)
    assert default_tenant.tier == old_tier


async def test_patch_tier_applies_for_superadmin(client, sa_headers, default_tenant, session):
    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}",
        json={"tier": "vip"},
        headers=sa_headers,
    )
    assert r.status_code == 200
    assert r.json()["tier"] == "vip"

    await session.refresh(default_tenant)
    assert default_tenant.tier == "vip"


async def test_patch_missing_tenant_404(client, sa_headers):
    r = await client.patch("/admin/tenants/999999", json={"display_name": "X"}, headers=sa_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /{tenant_id}/pause  and  /{tenant_id}/resume
# ---------------------------------------------------------------------------


async def _make_tenant_with_bot(session):
    """Create a fresh tenant with one TenantBot and return (tenant, bot)."""
    from quantuum.common.crypto import encrypt_token

    tenant = Tenant(slug="pausable", display_name="Pausable")
    session.add(tenant)
    await session.flush()
    bot = TenantBot(
        tenant_id=tenant.id,
        bot_username="pausablebot",
        bot_token_enc=encrypt_token("456:testtoken"),
        webhook_secret_path="pause-secret",
        status="active",
    )
    session.add(bot)
    await session.commit()
    await session.refresh(tenant)
    await session.refresh(bot)
    return tenant, bot


async def test_pause_sets_suspended_and_pauses_bot(client, sa_headers, session):
    tenant, bot = await _make_tenant_with_bot(session)

    r = await client.post(f"/admin/tenants/{tenant.id}/pause", headers=sa_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "suspended"

    await session.refresh(tenant)
    await session.refresh(bot)
    assert tenant.status == "suspended"
    assert bot.status == "paused"


async def test_pause_creates_audit_log(client, sa_headers, session):
    tenant, _bot = await _make_tenant_with_bot(session)

    await client.post(f"/admin/tenants/{tenant.id}/pause", headers=sa_headers)

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "tenant.pause",
            AuditLog.tenant_id == tenant.id,
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_resume_sets_active(client, sa_headers, session):
    tenant, bot = await _make_tenant_with_bot(session)
    # First pause
    tenant.status = "suspended"
    bot.status = "paused"
    session.add(tenant)
    session.add(bot)
    await session.commit()

    r = await client.post(f"/admin/tenants/{tenant.id}/resume", headers=sa_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    await session.refresh(tenant)
    await session.refresh(bot)
    assert tenant.status == "active"
    assert bot.status == "active"


async def test_resume_creates_audit_log(client, sa_headers, session):
    tenant, _bot = await _make_tenant_with_bot(session)
    tenant.status = "suspended"
    session.add(tenant)
    await session.commit()

    await client.post(f"/admin/tenants/{tenant.id}/resume", headers=sa_headers)

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "tenant.resume",
            AuditLog.tenant_id == tenant.id,
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_pause_platform_tenant_400(client, sa_headers, session):
    """Cannot pause the platform tenant."""
    platform = Tenant(slug="platform-test", display_name="Platform", is_platform=True)
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    r = await client.post(f"/admin/tenants/{platform.id}/pause", headers=sa_headers)
    assert r.status_code == 400


async def test_pause_by_owner(client, session, default_tenant):
    """Owner of the tenant can pause it."""
    headers = await _make_role_headers(session, default_tenant.id, "owner")
    r = await client.post(f"/admin/tenants/{default_tenant.id}/pause", headers=headers)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Task 15 — tenant-scoped audit-log read (owner/admin)
# ---------------------------------------------------------------------------


async def test_tenant_audit_log_scoped_to_this_tenant(
    client, owner_headers, session, default_tenant
):
    """GET /admin/tenants/{id}/audit-log returns only this tenant's entries."""
    from quantuum.domain.audit import record_audit

    # Another tenant with its own audit entry that must NOT leak.
    other = Tenant(slug="audit-other", display_name="Other")
    session.add(other)
    await session.flush()
    await record_audit(
        session,
        tenant_id=other.id,
        actor_account_id=None,
        action="tenant.update",
        entity_type="tenant",
        entity_id=other.id,
    )
    # An entry for THIS tenant.
    await record_audit(
        session,
        tenant_id=default_tenant.id,
        actor_account_id=None,
        action="config.update",
        entity_type="tenant_config",
        entity_id="k",
    )
    await session.commit()

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/audit-log", headers=owner_headers
    )
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 1
    assert all(e["tenant_id"] == default_tenant.id for e in entries)
    assert any(e["action"] == "config.update" for e in entries)


async def test_tenant_audit_log_customer_forbidden(
    client, customer_headers, default_tenant
):
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/audit-log", headers=customer_headers
    )
    assert r.status_code == 403
