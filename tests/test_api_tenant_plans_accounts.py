"""Tests for tenant-scoped plan CRUD and accounts list/balance admin.

Routes (Tasks 10 + 11, Plan 5b):
  GET    /admin/tenants/{tenant_id}/plans
  POST   /admin/tenants/{tenant_id}/plans/subscription
  POST   /admin/tenants/{tenant_id}/plans/package
  PATCH  /admin/tenants/{tenant_id}/plans/subscription/{plan_id}
  PATCH  /admin/tenants/{tenant_id}/plans/package/{plan_id}

  GET    /admin/tenants/{tenant_id}/accounts?limit=50&offset=0
  PATCH  /admin/tenants/{tenant_id}/accounts/{account_id}/balance
"""
from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import (
    Account,
    AccountBalance,
    AuditLog,
    PackagePlan,
    SubscriptionPlan,
    Tenant,
)
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


async def _make_role_headers(session, tenant_id: int, role: str) -> dict[str, str]:
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
    await session.commit()
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
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Task 10 — Plans CRUD
# ---------------------------------------------------------------------------


async def test_owner_create_subscription_plan_201(client, owner_headers, default_tenant):
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/plans/subscription",
        json={"slug": "monthly", "name": "Monthly", "period_days": 30, "price_cents": 500},
        headers=owner_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "monthly"
    assert body["tenant_id"] == default_tenant.id


async def test_owner_create_package_plan_201(client, owner_headers, default_tenant):
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/plans/package",
        json={"slug": "starter", "name": "Starter", "request_count": 10, "price_cents": 100},
        headers=owner_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "starter"
    assert body["tenant_id"] == default_tenant.id


async def test_get_plans_returns_only_tenant_plans(client, owner_headers, default_tenant, session):
    """GET /plans returns only this tenant's plans; global (NULL) and other-tenant excluded."""
    # Seed a global plan (tenant_id=NULL)
    global_sub = SubscriptionPlan(
        tenant_id=None, slug="global-sub", name="Global Sub",
        period_days=365, price_cents=9999,
    )
    session.add(global_sub)

    # Seed another tenant + its plan
    other = Tenant(slug="other-plans", display_name="Other")
    session.add(other)
    await session.flush()
    other_sub = SubscriptionPlan(
        tenant_id=other.id, slug="other-sub", name="Other Sub",
        period_days=30, price_cents=200,
    )
    session.add(other_sub)

    # Seed a plan belonging to this tenant
    my_sub = SubscriptionPlan(
        tenant_id=default_tenant.id, slug="mine-sub", name="Mine Sub",
        period_days=60, price_cents=300,
    )
    session.add(my_sub)
    await session.commit()

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/plans",
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    slugs = [p["slug"] for p in body["subscriptions"]]
    assert "mine-sub" in slugs
    assert "global-sub" not in slugs
    assert "other-sub" not in slugs


async def test_get_plans_excludes_global_packages(client, owner_headers, default_tenant, session):
    global_pkg = PackagePlan(
        tenant_id=None, slug="global-pkg", name="Global Pkg",
        request_count=50, price_cents=500,
    )
    my_pkg = PackagePlan(
        tenant_id=default_tenant.id, slug="my-pkg", name="My Pkg",
        request_count=5, price_cents=50,
    )
    session.add(global_pkg)
    session.add(my_pkg)
    await session.commit()

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/plans",
        headers=owner_headers,
    )
    assert r.status_code == 200
    pkg_slugs = [p["slug"] for p in r.json()["packages"]]
    assert "my-pkg" in pkg_slugs
    assert "global-pkg" not in pkg_slugs


async def test_patch_subscription_plan_updates_price(
    client, owner_headers, default_tenant, session
):
    plan = SubscriptionPlan(
        tenant_id=default_tenant.id, slug="patch-sub", name="Patch Sub",
        period_days=30, price_cents=100,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/plans/subscription/{plan.id}",
        json={"price_cents": 999, "active": False},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["price_cents"] == 999
    assert body["active"] is False


async def test_patch_package_plan_updates_fields(
    client, owner_headers, default_tenant, session
):
    plan = PackagePlan(
        tenant_id=default_tenant.id, slug="patch-pkg", name="Patch Pkg",
        request_count=10, price_cents=200,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/plans/package/{plan.id}",
        json={"request_count": 20, "active": False},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["request_count"] == 20
    assert body["active"] is False


async def test_patch_subscription_plan_wrong_tenant_404(
    client, owner_headers, default_tenant, session
):
    """PATCH a subscription plan belonging to another tenant → 404."""
    other = Tenant(slug="other-for-patch", display_name="Other")
    session.add(other)
    await session.flush()
    plan = SubscriptionPlan(
        tenant_id=other.id, slug="other-sub-patch", name="Other",
        period_days=30, price_cents=100,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/plans/subscription/{plan.id}",
        json={"price_cents": 1},
        headers=owner_headers,
    )
    assert r.status_code == 404


async def test_patch_package_plan_wrong_tenant_404(
    client, owner_headers, default_tenant, session
):
    other = Tenant(slug="other-for-pkg-patch", display_name="Other")
    session.add(other)
    await session.flush()
    plan = PackagePlan(
        tenant_id=other.id, slug="other-pkg-patch", name="Other",
        request_count=5, price_cents=100,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/plans/package/{plan.id}",
        json={"price_cents": 1},
        headers=owner_headers,
    )
    assert r.status_code == 404


async def test_customer_cannot_create_plan_403(client, customer_headers, default_tenant):
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/plans/subscription",
        json={"slug": "x", "name": "X", "period_days": 30, "price_cents": 1},
        headers=customer_headers,
    )
    assert r.status_code == 403


async def test_plan_create_writes_audit(client, owner_headers, default_tenant, session):
    await client.post(
        f"/admin/tenants/{default_tenant.id}/plans/subscription",
        json={"slug": "audit-sub", "name": "Audit Sub", "period_days": 30, "price_cents": 1},
        headers=owner_headers,
    )
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "plan.create",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.entity_type == "subscription_plan"


async def test_plan_update_writes_audit(client, owner_headers, default_tenant, session):
    plan = SubscriptionPlan(
        tenant_id=default_tenant.id, slug="audit-patch", name="Audit",
        period_days=30, price_cents=100,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    await client.patch(
        f"/admin/tenants/{default_tenant.id}/plans/subscription/{plan.id}",
        json={"price_cents": 200},
        headers=owner_headers,
    )

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "plan.update",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.entity_type == "subscription_plan"


# ---------------------------------------------------------------------------
# Task 11 — Accounts list + balance
# ---------------------------------------------------------------------------


async def test_accounts_list_returns_tenant_only(
    client, owner_headers, default_tenant, session
):
    """GET /accounts lists only this tenant's accounts, not another tenant's."""
    # Seed 2 accounts in this tenant
    a1 = Account(tenant_id=default_tenant.id)
    a2 = Account(tenant_id=default_tenant.id)
    session.add(a1)
    session.add(a2)
    await session.flush()

    # Seed 1 account in another tenant
    other = Tenant(slug="other-accs", display_name="Other")
    session.add(other)
    await session.flush()
    a_other = Account(tenant_id=other.id)
    session.add(a_other)
    await session.commit()
    await session.refresh(a1)
    await session.refresh(a2)
    await session.refresh(a_other)

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/accounts",
        headers=owner_headers,
    )
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()}
    assert a1.id in ids
    assert a2.id in ids
    assert a_other.id not in ids


async def test_accounts_list_includes_balance_fields(
    client, owner_headers, default_tenant, session
):
    """Account list items include package_credits and subscription_active_until."""
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    bal = AccountBalance(account_id=acc.id, package_credits=42)
    session.add(bal)
    await session.commit()
    await session.refresh(acc)

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/accounts",
        headers=owner_headers,
    )
    assert r.status_code == 200
    found = next((item for item in r.json() if item["id"] == acc.id), None)
    assert found is not None
    assert found["package_credits"] == 42
    assert found["subscription_active_until"] is None


async def test_accounts_list_no_balance_row_defaults_zero(
    client, owner_headers, default_tenant, session
):
    """Accounts without an AccountBalance row get package_credits=0."""
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/accounts",
        headers=owner_headers,
    )
    assert r.status_code == 200
    found = next((item for item in r.json() if item["id"] == acc.id), None)
    assert found is not None
    assert found["package_credits"] == 0


async def test_customer_cannot_list_accounts_403(client, customer_headers, default_tenant):
    r = await client.get(
        f"/admin/tenants/{default_tenant.id}/accounts",
        headers=customer_headers,
    )
    assert r.status_code == 403


async def test_patch_balance_sets_credits(client, owner_headers, default_tenant, session):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"package_credits": 100},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == acc.id
    assert body["package_credits"] == 100


async def test_patch_balance_sets_subscription_until(
    client, owner_headers, default_tenant, session
):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    until = "2030-01-01T00:00:00Z"
    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"subscription_active_until": until},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["subscription_active_until"] is not None


async def test_patch_balance_creates_balance_row(
    client, owner_headers, default_tenant, session
):
    """Patching balance when no AccountBalance exists creates a new row."""
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"package_credits": 55},
        headers=owner_headers,
    )
    assert r.status_code == 200

    bal = await session.get(AccountBalance, acc.id)
    assert bal is not None
    assert bal.package_credits == 55


async def test_patch_balance_out_of_tenant_404(
    client, owner_headers, default_tenant, session
):
    """Patching balance for an account in another tenant → 404."""
    other = Tenant(slug="other-bal", display_name="Other")
    session.add(other)
    await session.flush()
    acc = Account(tenant_id=other.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"package_credits": 1},
        headers=owner_headers,
    )
    assert r.status_code == 404


async def test_patch_balance_writes_audit(client, owner_headers, default_tenant, session):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"package_credits": 7},
        headers=owner_headers,
    )

    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "account.balance_adjust",
            AuditLog.tenant_id == default_tenant.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert "before" in log.payload_jsonb
    assert "after" in log.payload_jsonb


async def test_customer_cannot_patch_balance_403(
    client, customer_headers, default_tenant, session
):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"package_credits": 1},
        headers=customer_headers,
    )
    assert r.status_code == 403


async def test_patch_balance_partial_update_preserves_other_fields(
    client, owner_headers, default_tenant, session
):
    """Patching only package_credits does not clear subscription_active_until."""
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    until = datetime(2030, 6, 1, tzinfo=timezone.utc)
    bal = AccountBalance(
        account_id=acc.id,
        package_credits=10,
        subscription_active_until=until,
    )
    session.add(bal)
    await session.commit()
    await session.refresh(acc)

    r = await client.patch(
        f"/admin/tenants/{default_tenant.id}/accounts/{acc.id}/balance",
        json={"package_credits": 99},
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["package_credits"] == 99
    assert body["subscription_active_until"] is not None  # preserved
