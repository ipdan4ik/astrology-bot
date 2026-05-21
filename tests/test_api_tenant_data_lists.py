"""Tests for per-account/tenant read lists (Plan 5d Task 5):
GET /admin/tenants/{tenant_id}/accounts/{account_id}
GET /admin/tenants/{tenant_id}/blueprints
GET /admin/tenants/{tenant_id}/requests
GET /admin/tenants/{tenant_id}/payments
"""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    Blueprint,
    NatalProfile,
    Payment,
    Request,
    Tenant,
)
from quantuum.domain.tenants import grant_role


# ---------------------------------------------------------------------------
# Fixtures (replicated from tests/test_api_admin_tenants.py)
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
async def customer_headers(session, default_tenant):
    """A regular customer in the tenant with no owner/admin role."""
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _make_account(session, tenant_id: int) -> Account:
    acc = Account(tenant_id=tenant_id)
    session.add(acc)
    await session.flush()
    return acc


async def _make_natal_profile(session, tenant_id: int, account_id: int) -> NatalProfile:
    np = NatalProfile(
        tenant_id=tenant_id,
        account_id=account_id,
        full_name="Test Person",
        birth_date=date(1990, 1, 1),
        birth_time=time(12, 0),
        birth_place="Moscow",
        latitude=Decimal("55.75"),
        longitude=Decimal("37.62"),
        timezone="Europe/Moscow",
    )
    session.add(np)
    await session.flush()
    return np


@pytest_asyncio.fixture
async def seeded(session, default_tenant):
    """Tenant T with 2 accounts; one account has a Blueprint(done) + Request +
    Payment(paid) + AccountBalance. A SECOND tenant gets its own data to confirm
    tenant scoping. Returns a dict of useful ids/objects."""
    t = default_tenant

    acc1 = await _make_account(session, t.id)
    acc2 = await _make_account(session, t.id)

    bal = AccountBalance(
        account_id=acc1.id,
        package_credits=7,
        subscription_active_until=utcnow() + timedelta(days=30),
        free_trial_used=True,
    )
    session.add(bal)

    np1 = await _make_natal_profile(session, t.id, acc1.id)
    bp1 = Blueprint(
        tenant_id=t.id,
        account_id=acc1.id,
        natal_profile_id=np1.id,
        status="done",
        completed_at=utcnow(),
    )
    session.add(bp1)
    req1 = Request(tenant_id=t.id, account_id=acc1.id, kind="blueprint", status="done")
    session.add(req1)
    pay1 = Payment(
        tenant_id=t.id,
        account_id=acc1.id,
        amount_cents=500,
        currency="XTR",
        status="paid",
        paid_at=utcnow(),
    )
    session.add(pay1)

    # Second tenant with its own data — must NOT leak into T's lists.
    other = Tenant(slug="other-data", display_name="Other")
    session.add(other)
    await session.flush()
    oacc = await _make_account(session, other.id)
    onp = await _make_natal_profile(session, other.id, oacc.id)
    obp = Blueprint(
        tenant_id=other.id,
        account_id=oacc.id,
        natal_profile_id=onp.id,
        status="done",
    )
    session.add(obp)
    oreq = Request(
        tenant_id=other.id, account_id=oacc.id, kind="blueprint", status="done"
    )
    session.add(oreq)
    opay = Payment(
        tenant_id=other.id, account_id=oacc.id, amount_cents=999, status="paid"
    )
    session.add(opay)

    await session.commit()
    await session.refresh(acc1)
    await session.refresh(acc2)
    await session.refresh(bal)

    return {
        "tenant": t,
        "acc1": acc1,
        "acc2": acc2,
        "other": other,
        "oacc": oacc,
    }


# ---------------------------------------------------------------------------
# GET /{tenant_id}/accounts/{account_id}  — account detail
# ---------------------------------------------------------------------------


async def test_account_detail_owner_200_with_balance(client, owner_headers, seeded):
    t = seeded["tenant"]
    acc1 = seeded["acc1"]
    r = await client.get(
        f"/admin/tenants/{t.id}/accounts/{acc1.id}", headers=owner_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == acc1.id
    assert body["package_credits"] == 7
    assert body["subscription_active_until"] is not None
    assert body["free_trial_used"] is True
    assert "created_at" in body
    assert "last_seen_at" in body


async def test_account_detail_no_balance_defaults(client, owner_headers, seeded):
    t = seeded["tenant"]
    acc2 = seeded["acc2"]
    r = await client.get(
        f"/admin/tenants/{t.id}/accounts/{acc2.id}", headers=owner_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["package_credits"] == 0
    assert body["subscription_active_until"] is None
    assert body["free_trial_used"] is False


async def test_account_detail_cross_tenant_404(client, owner_headers, seeded):
    t = seeded["tenant"]
    oacc = seeded["oacc"]  # belongs to the *other* tenant
    r = await client.get(
        f"/admin/tenants/{t.id}/accounts/{oacc.id}", headers=owner_headers
    )
    assert r.status_code == 404


async def test_account_detail_missing_404(client, owner_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(
        f"/admin/tenants/{t.id}/accounts/999999", headers=owner_headers
    )
    assert r.status_code == 404


async def test_account_detail_customer_403(client, customer_headers, seeded):
    t = seeded["tenant"]
    acc1 = seeded["acc1"]
    r = await client.get(
        f"/admin/tenants/{t.id}/accounts/{acc1.id}", headers=customer_headers
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /{tenant_id}/blueprints
# ---------------------------------------------------------------------------


async def test_blueprints_scoped_to_tenant(client, owner_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(f"/admin/tenants/{t.id}/blueprints", headers=owner_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["account_id"] == seeded["acc1"].id
    assert rows[0]["status"] == "done"
    assert rows[0]["completed_at"] is not None


async def test_blueprints_newest_first_and_pagination(client, owner_headers, seeded, session):
    t = seeded["tenant"]
    # Add two more blueprints (fresh accounts; NatalProfile.account_id is unique)
    # so we have 3 total for tenant T.
    acc_a = await _make_account(session, t.id)
    np_a = await _make_natal_profile(session, t.id, acc_a.id)
    bp_a = Blueprint(tenant_id=t.id, account_id=acc_a.id, natal_profile_id=np_a.id, status="pending")
    session.add(bp_a)
    await session.flush()
    acc_b = await _make_account(session, t.id)
    np_b = await _make_natal_profile(session, t.id, acc_b.id)
    bp_b = Blueprint(tenant_id=t.id, account_id=acc_b.id, natal_profile_id=np_b.id, status="failed")
    session.add(bp_b)
    await session.commit()
    await session.refresh(bp_a)
    await session.refresh(bp_b)

    r = await client.get(f"/admin/tenants/{t.id}/blueprints", headers=owner_headers)
    rows = r.json()
    assert len(rows) == 3
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids, reverse=True)  # newest (highest id) first

    # limit/offset
    r2 = await client.get(
        f"/admin/tenants/{t.id}/blueprints?limit=1&offset=1", headers=owner_headers
    )
    rows2 = r2.json()
    assert len(rows2) == 1
    assert rows2[0]["id"] == ids[1]


async def test_blueprints_customer_403(client, customer_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(f"/admin/tenants/{t.id}/blueprints", headers=customer_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /{tenant_id}/requests
# ---------------------------------------------------------------------------


async def test_requests_scoped_to_tenant(client, owner_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(f"/admin/tenants/{t.id}/requests", headers=owner_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["account_id"] == seeded["acc1"].id
    assert rows[0]["kind"] == "blueprint"
    assert rows[0]["status"] == "done"


async def test_requests_newest_first_and_pagination(client, owner_headers, seeded, session):
    t = seeded["tenant"]
    acc1 = seeded["acc1"]
    r_a = Request(tenant_id=t.id, account_id=acc1.id, kind="blueprint", status="pending")
    r_b = Request(tenant_id=t.id, account_id=acc1.id, kind="blueprint", status="failed")
    session.add(r_a)
    session.add(r_b)
    await session.commit()

    r = await client.get(f"/admin/tenants/{t.id}/requests", headers=owner_headers)
    rows = r.json()
    assert len(rows) == 3
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids, reverse=True)

    r2 = await client.get(
        f"/admin/tenants/{t.id}/requests?limit=2&offset=1", headers=owner_headers
    )
    rows2 = r2.json()
    assert len(rows2) == 2
    assert [row["id"] for row in rows2] == ids[1:3]


async def test_requests_customer_403(client, customer_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(f"/admin/tenants/{t.id}/requests", headers=customer_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /{tenant_id}/payments
# ---------------------------------------------------------------------------


async def test_payments_scoped_to_tenant(client, owner_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(f"/admin/tenants/{t.id}/payments", headers=owner_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["account_id"] == seeded["acc1"].id
    assert rows[0]["amount_cents"] == 500
    assert rows[0]["currency"] == "XTR"
    assert rows[0]["status"] == "paid"
    assert rows[0]["paid_at"] is not None


async def test_payments_newest_first_and_pagination(client, owner_headers, seeded, session):
    t = seeded["tenant"]
    acc1 = seeded["acc1"]
    p_a = Payment(tenant_id=t.id, account_id=acc1.id, amount_cents=100, status="pending")
    p_b = Payment(tenant_id=t.id, account_id=acc1.id, amount_cents=200, status="failed")
    session.add(p_a)
    session.add(p_b)
    await session.commit()

    r = await client.get(f"/admin/tenants/{t.id}/payments", headers=owner_headers)
    rows = r.json()
    assert len(rows) == 3
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids, reverse=True)

    r2 = await client.get(
        f"/admin/tenants/{t.id}/payments?limit=1&offset=2", headers=owner_headers
    )
    rows2 = r2.json()
    assert len(rows2) == 1
    assert rows2[0]["id"] == ids[2]


async def test_payments_customer_403(client, customer_headers, seeded):
    t = seeded["tenant"]
    r = await client.get(f"/admin/tenants/{t.id}/payments", headers=customer_headers)
    assert r.status_code == 403
