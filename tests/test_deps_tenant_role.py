"""Unit tests for the require_tenant_role dependency factory."""
import pytest
from fastapi import HTTPException

from quantuum.db.models import Account, Tenant
from quantuum.domain.tenants import grant_role


pytestmark = pytest.mark.asyncio


async def _make_account(session, *, tenant_id, is_superadmin=False) -> Account:
    acc = Account(tenant_id=tenant_id, is_superadmin=is_superadmin)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


@pytest.fixture
async def other_tenant(session) -> Tenant:
    t = Tenant(slug="other", display_name="Other")
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


# ── superadmin bypass ────────────────────────────────────────────────────────

async def test_superadmin_passes_any_tenant(session, default_tenant):
    from quantuum.api.deps import require_tenant_role

    superadmin = await _make_account(session, tenant_id=None, is_superadmin=True)
    dep = require_tenant_role(("owner",))
    result = await dep(tenant_id=default_tenant.id, account=superadmin, session=session)
    assert result is superadmin


# ── owner ────────────────────────────────────────────────────────────────────

async def test_owner_passes_owner_role(session, default_tenant):
    from quantuum.api.deps import require_tenant_role

    owner = await _make_account(session, tenant_id=default_tenant.id)
    await grant_role(session, tenant_id=default_tenant.id, account_id=owner.id, role="owner")

    dep = require_tenant_role(("owner",))
    result = await dep(tenant_id=default_tenant.id, account=owner, session=session)
    assert result is owner


async def test_owner_passes_owner_admin_roles(session, default_tenant):
    from quantuum.api.deps import require_tenant_role

    owner = await _make_account(session, tenant_id=default_tenant.id)
    await grant_role(session, tenant_id=default_tenant.id, account_id=owner.id, role="owner")

    dep = require_tenant_role(("owner", "admin"))
    result = await dep(tenant_id=default_tenant.id, account=owner, session=session)
    assert result is owner


# ── admin ────────────────────────────────────────────────────────────────────

async def test_admin_passes_owner_admin_roles(session, default_tenant):
    from quantuum.api.deps import require_tenant_role

    admin = await _make_account(session, tenant_id=default_tenant.id)
    await grant_role(session, tenant_id=default_tenant.id, account_id=admin.id, role="admin")

    dep = require_tenant_role(("owner", "admin"))
    result = await dep(tenant_id=default_tenant.id, account=admin, session=session)
    assert result is admin


async def test_admin_fails_owner_only_roles(session, default_tenant):
    from quantuum.api.deps import require_tenant_role

    admin = await _make_account(session, tenant_id=default_tenant.id)
    await grant_role(session, tenant_id=default_tenant.id, account_id=admin.id, role="admin")

    dep = require_tenant_role(("owner",))
    with pytest.raises(HTTPException) as exc_info:
        await dep(tenant_id=default_tenant.id, account=admin, session=session)
    assert exc_info.value.status_code == 403


# ── plain customer (no role) ─────────────────────────────────────────────────

async def test_plain_customer_fails(session, default_tenant):
    from quantuum.api.deps import require_tenant_role

    customer = await _make_account(session, tenant_id=default_tenant.id)

    dep = require_tenant_role(("owner", "admin"))
    with pytest.raises(HTTPException) as exc_info:
        await dep(tenant_id=default_tenant.id, account=customer, session=session)
    assert exc_info.value.status_code == 403


# ── cross-tenant ─────────────────────────────────────────────────────────────

async def test_cross_tenant_account_fails(session, default_tenant, other_tenant):
    from quantuum.api.deps import require_tenant_role

    other_owner = await _make_account(session, tenant_id=other_tenant.id)
    await grant_role(
        session, tenant_id=other_tenant.id, account_id=other_owner.id, role="owner"
    )

    dep = require_tenant_role(("owner", "admin"))
    with pytest.raises(HTTPException) as exc_info:
        await dep(tenant_id=default_tenant.id, account=other_owner, session=session)
    assert exc_info.value.status_code == 403
