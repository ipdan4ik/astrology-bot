"""Tests for tenant roles CRUD and ownership transfer.

Routes:
  GET    /admin/tenants/{tenant_id}/roles          (owner + admin)
  POST   /admin/tenants/{tenant_id}/roles          (owner-only)
  DELETE /admin/tenants/{tenant_id}/roles/{role_id} (owner-only)
  POST   /admin/tenants/{tenant_id}/transfer        (owner-only)
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import Account, AuditLog, Tenant, TenantRole
from quantuum.domain.tenants import grant_role


# ---------------------------------------------------------------------------
# Fixtures (mirror test_api_admin_tenants.py helpers)
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


async def _make_role_headers(session, tenant_id: int, role: str) -> dict[str, str]:
    """Create an account in the tenant, grant role, return (account, auth headers)."""
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


async def _make_role_headers_with_account(
    session, tenant_id: int, role: str
) -> tuple[Account, dict[str, str]]:
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
    return acc, {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def owner_headers(session, default_tenant):
    return await _make_role_headers(session, default_tenant.id, "owner")


@pytest_asyncio.fixture
async def owner_account_and_headers(session, default_tenant):
    return await _make_role_headers_with_account(session, default_tenant.id, "owner")


@pytest_asyncio.fixture
async def admin_headers(session, default_tenant):
    return await _make_role_headers(session, default_tenant.id, "admin")


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /{tenant_id}/roles  — auth matrix
# ---------------------------------------------------------------------------


async def test_list_roles_owner_200(client, owner_headers, default_tenant):
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/roles", headers=owner_headers
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_list_roles_admin_200(client, admin_headers, default_tenant):
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/roles", headers=admin_headers
    )
    assert r.status_code == 200


async def test_list_roles_customer_403(client, customer_headers, default_tenant):
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/roles", headers=customer_headers
    )
    assert r.status_code == 403


async def test_list_roles_returns_role_fields(client, owner_headers, default_tenant):
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/roles", headers=owner_headers
    )
    assert r.status_code == 200
    rows = r.json()
    # At least the owner role exists (created by owner_headers fixture)
    assert len(rows) >= 1
    row = rows[0]
    assert "id" in row
    assert "account_id" in row
    assert "role" in row
    assert "granted_at" in row


# ---------------------------------------------------------------------------
# POST /{tenant_id}/roles — grant
# ---------------------------------------------------------------------------


async def test_grant_role_owner_201(client, owner_headers, default_tenant, session):
    """Owner can grant a role to an in-tenant account."""
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.commit()
    await session.refresh(target)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": target.id, "role": "admin"},
        headers=owner_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["account_id"] == target.id
    assert body["role"] == "admin"
    assert "id" in body
    assert "granted_at" in body


async def test_grant_role_creates_audit(client, owner_headers, default_tenant, session):
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.commit()
    await session.refresh(target)

    await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": target.id, "role": "admin"},
        headers=owner_headers,
    )

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "role.grant",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.entity_type == "tenant_role"
    assert log.payload_jsonb["account_id"] == target.id
    assert log.payload_jsonb["role"] == "admin"


async def test_grant_role_admin_403(client, admin_headers, default_tenant, session):
    """Admin is NOT allowed to grant roles (owner-only)."""
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.commit()
    await session.refresh(target)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": target.id, "role": "admin"},
        headers=admin_headers,
    )
    assert r.status_code == 403


async def test_grant_role_invalid_role_400(
    client, owner_headers, default_tenant, session
):
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.commit()
    await session.refresh(target)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": target.id, "role": "superuser"},
        headers=owner_headers,
    )
    assert r.status_code == 400


async def test_grant_role_out_of_tenant_400(
    client, owner_headers, default_tenant, session
):
    """Granting a role to an account from another tenant → 400."""
    other_tenant = Tenant(slug="other-for-roles", display_name="Other")
    session.add(other_tenant)
    await session.flush()
    foreign_acc = Account(tenant_id=other_tenant.id)
    session.add(foreign_acc)
    await session.commit()
    await session.refresh(foreign_acc)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": foreign_acc.id, "role": "admin"},
        headers=owner_headers,
    )
    assert r.status_code == 400


async def test_grant_role_duplicate_409(client, owner_headers, default_tenant, session):
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.commit()
    await session.refresh(target)

    # First grant succeeds
    r1 = await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": target.id, "role": "admin"},
        headers=owner_headers,
    )
    assert r1.status_code == 201

    # Second identical grant → 409
    r2 = await client.post(
        f"/admin/tenants/{default_tenant.id}/roles",
        json={"account_id": target.id, "role": "admin"},
        headers=owner_headers,
    )
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /{tenant_id}/roles/{role_id}
# ---------------------------------------------------------------------------


async def test_revoke_role_owner_204(client, owner_headers, default_tenant, session):
    """Owner can revoke an admin role."""
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.flush()
    role = TenantRole(
        tenant_id=default_tenant.id, account_id=target.id, role="admin"
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)

    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/roles/{role.id}",
        headers=owner_headers,
    )
    assert r.status_code in (200, 204)


async def test_revoke_role_creates_audit(client, owner_headers, default_tenant, session):
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.flush()
    role = TenantRole(
        tenant_id=default_tenant.id, account_id=target.id, role="admin"
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)

    await client.delete(
        f"/admin/tenants/{default_tenant.id}/roles/{role.id}",
        headers=owner_headers,
    )

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "role.revoke",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_revoke_role_admin_403(client, admin_headers, default_tenant, session):
    target = Account(tenant_id=default_tenant.id)
    session.add(target)
    await session.flush()
    role = TenantRole(
        tenant_id=default_tenant.id, account_id=target.id, role="admin"
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)

    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/roles/{role.id}",
        headers=admin_headers,
    )
    assert r.status_code == 403


async def test_revoke_role_missing_404(client, owner_headers, default_tenant):
    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/roles/999999",
        headers=owner_headers,
    )
    assert r.status_code == 404


async def test_revoke_last_owner_400(client, owner_account_and_headers, default_tenant, session):
    """Cannot remove the sole owner role."""
    owner_acc, headers = owner_account_and_headers

    # Find the owner role for this account
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == default_tenant.id,
            TenantRole.account_id == owner_acc.id,
            TenantRole.role == "owner",
        )
    )
    owner_role = result.scalar_one()

    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/roles/{owner_role.id}",
        headers=headers,
    )
    assert r.status_code == 400


async def test_revoke_owner_role_ok_when_multiple_owners(
    client, owner_account_and_headers, default_tenant, session
):
    """When there are ≥2 owners, removing one is allowed."""
    owner_acc, headers = owner_account_and_headers

    # Add a second owner
    second = Account(tenant_id=default_tenant.id)
    session.add(second)
    await session.flush()
    role2 = TenantRole(
        tenant_id=default_tenant.id, account_id=second.id, role="owner"
    )
    session.add(role2)
    await session.commit()
    await session.refresh(role2)

    # Find the first owner's role
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == default_tenant.id,
            TenantRole.account_id == owner_acc.id,
            TenantRole.role == "owner",
        )
    )
    owner_role = result.scalar_one()

    r = await client.delete(
        f"/admin/tenants/{default_tenant.id}/roles/{owner_role.id}",
        headers=headers,
    )
    assert r.status_code in (200, 204)


# ---------------------------------------------------------------------------
# POST /{tenant_id}/transfer
# ---------------------------------------------------------------------------


async def test_transfer_ownership_200(
    client, owner_account_and_headers, default_tenant, session
):
    """Owner transfers ownership to another in-tenant account."""
    _owner_acc, headers = owner_account_and_headers

    new_owner = Account(tenant_id=default_tenant.id)
    session.add(new_owner)
    await session.commit()
    await session.refresh(new_owner)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/transfer",
        json={"new_owner_account_id": new_owner.id},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["primary_owner_account_id"] == new_owner.id


async def test_transfer_grants_owner_role(
    client, owner_account_and_headers, default_tenant, session
):
    _owner_acc, headers = owner_account_and_headers

    new_owner = Account(tenant_id=default_tenant.id)
    session.add(new_owner)
    await session.commit()
    await session.refresh(new_owner)

    await client.post(
        f"/admin/tenants/{default_tenant.id}/transfer",
        json={"new_owner_account_id": new_owner.id},
        headers=headers,
    )

    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == default_tenant.id,
            TenantRole.account_id == new_owner.id,
            TenantRole.role == "owner",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_transfer_creates_audit(
    client, owner_account_and_headers, default_tenant, session
):
    owner_acc, headers = owner_account_and_headers

    # Set primary_owner so we can check before/after
    default_tenant.primary_owner_account_id = owner_acc.id
    session.add(default_tenant)
    await session.commit()

    new_owner = Account(tenant_id=default_tenant.id)
    session.add(new_owner)
    await session.commit()
    await session.refresh(new_owner)

    await client.post(
        f"/admin/tenants/{default_tenant.id}/transfer",
        json={"new_owner_account_id": new_owner.id},
        headers=headers,
    )

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "tenant.transfer",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.payload_jsonb["after_primary"] == new_owner.id


async def test_transfer_non_owner_403(client, admin_headers, default_tenant, session):
    new_owner = Account(tenant_id=default_tenant.id)
    session.add(new_owner)
    await session.commit()
    await session.refresh(new_owner)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/transfer",
        json={"new_owner_account_id": new_owner.id},
        headers=admin_headers,
    )
    assert r.status_code == 403


async def test_transfer_out_of_tenant_account_400(
    client, owner_headers, default_tenant, session
):
    other_tenant = Tenant(slug="other-for-transfer", display_name="Other")
    session.add(other_tenant)
    await session.flush()
    foreign_acc = Account(tenant_id=other_tenant.id)
    session.add(foreign_acc)
    await session.commit()
    await session.refresh(foreign_acc)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/transfer",
        json={"new_owner_account_id": foreign_acc.id},
        headers=owner_headers,
    )
    assert r.status_code == 400


async def test_transfer_revoke_previous(
    client, owner_account_and_headers, default_tenant, session
):
    """With revoke_previous=True the prior primary owner loses the owner role."""
    owner_acc, headers = owner_account_and_headers

    # Set primary owner
    default_tenant.primary_owner_account_id = owner_acc.id
    session.add(default_tenant)
    await session.commit()

    new_owner = Account(tenant_id=default_tenant.id)
    session.add(new_owner)
    await session.commit()
    await session.refresh(new_owner)

    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/transfer",
        json={"new_owner_account_id": new_owner.id, "revoke_previous": True},
        headers=headers,
    )
    assert r.status_code == 200

    # The old owner should no longer have the "owner" role
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == default_tenant.id,
            TenantRole.account_id == owner_acc.id,
            TenantRole.role == "owner",
        )
    )
    assert result.scalar_one_or_none() is None
