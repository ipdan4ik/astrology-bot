"""Tests for platform-wide stats + per-tenant breakdown + onboarding funnel (Plan 5b, Task 13).

Route: GET /admin/platform/stats?period_days=30 (superadmin, read-only)
Domain: quantuum.domain.stats.platform_stats
"""
from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountIdentity,
    Payment,
    Request,
    Tenant,
    TenantInvite,
)
from quantuum.domain.stats import platform_stats


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
async def seeded_platform(session, default_tenant):
    """Seed 2 non-platform tenants (besides the default) plus invites.

    default_tenant (slug="default") is NOT a platform tenant by default
    (is_platform defaults to False), so we mark it as platform here to make
    the per-tenant breakdown deterministic (only tenant-a and tenant-b show up).
    """
    now = utcnow()

    # Mark the default tenant as the platform tenant so it's excluded from
    # the per-tenant breakdown and active_tenants funnel count.
    default_tenant.is_platform = True
    session.add(default_tenant)
    await session.flush()

    # --- tenant A (active) ---
    ta = Tenant(slug="tenant-a", display_name="Tenant A", status="active")
    # --- tenant B (active) ---
    tb = Tenant(slug="tenant-b", display_name="Tenant B", status="active")
    session.add_all([ta, tb])
    await session.flush()
    await session.refresh(ta)
    await session.refresh(tb)

    # --- accounts ---
    # tenant A: 2 accounts, both seen recently
    a1 = Account(tenant_id=ta.id, last_seen_at=now - timedelta(hours=2))
    a2 = Account(tenant_id=ta.id, last_seen_at=now - timedelta(days=2))
    # tenant B: 1 account, seen recently
    b1 = Account(tenant_id=tb.id, last_seen_at=now - timedelta(hours=5))
    # platform tenant: 1 internal account (master-bot onboarding activity) — must NOT be counted
    p_acc = Account(tenant_id=default_tenant.id, last_seen_at=now - timedelta(hours=1))
    session.add_all([a1, a2, b1, p_acc])
    await session.flush()
    await session.refresh(a1)
    await session.refresh(a2)
    await session.refresh(b1)
    await session.refresh(p_acc)

    # --- payments (paid within 30-day window) ---
    # tenant A: 2 paid customers, revenue 500 + 700 = 1200
    pa1 = Payment(
        tenant_id=ta.id,
        account_id=a1.id,
        amount_cents=500,
        currency="XTR",
        status="paid",
        paid_at=now - timedelta(days=1),
    )
    pa2 = Payment(
        tenant_id=ta.id,
        account_id=a2.id,
        amount_cents=700,
        currency="XTR",
        status="paid",
        paid_at=now - timedelta(days=3),
    )
    # tenant B: 1 paid customer, revenue 900
    pb1 = Payment(
        tenant_id=tb.id,
        account_id=b1.id,
        amount_cents=900,
        currency="XTR",
        status="paid",
        paid_at=now - timedelta(days=2),
    )
    # platform tenant: 1 internal paid payment — must NOT be counted
    p_pay = Payment(
        tenant_id=default_tenant.id,
        account_id=p_acc.id,
        amount_cents=9999,
        currency="XTR",
        status="paid",
        paid_at=now - timedelta(days=1),
    )
    session.add_all([pa1, pa2, pb1, p_pay])
    await session.flush()

    # --- requests in window ---
    # tenant A: 2 blueprint
    ra1 = Request(
        tenant_id=ta.id, account_id=a1.id, kind="blueprint", created_at=now - timedelta(days=1)
    )
    ra2 = Request(
        tenant_id=ta.id, account_id=a2.id, kind="blueprint", created_at=now - timedelta(days=2)
    )
    # tenant B: 1 profile
    rb1 = Request(
        tenant_id=tb.id, account_id=b1.id, kind="profile", created_at=now - timedelta(days=1)
    )
    session.add_all([ra1, ra2, rb1])
    await session.flush()

    # --- invites ---
    # 3 issued; 1 used (status="used"), 1 used via used_count>0, 1 active/unused
    inv_used = TenantInvite(code="INV-USED", status="used", used_count=1, max_uses=1)
    inv_partial = TenantInvite(code="INV-PARTIAL", status="active", used_count=1, max_uses=3)
    inv_unused = TenantInvite(code="INV-UNUSED", status="active", used_count=0, max_uses=1)
    session.add_all([inv_used, inv_partial, inv_unused])
    await session.flush()

    await session.commit()
    await session.refresh(ta)
    await session.refresh(tb)
    return {"tenant_a": ta, "tenant_b": tb, "default": default_tenant, "platform_account": p_acc, "platform_payment": p_pay}


# ---------------------------------------------------------------------------
# Domain-layer tests
# ---------------------------------------------------------------------------


async def test_platform_stats_aggregates(session, seeded_platform):
    ta = seeded_platform["tenant_a"]
    tb = seeded_platform["tenant_b"]

    stats = await platform_stats(session, period_days=30)

    # Global headline metrics must EXCLUDE the platform tenant's internal data.
    # The platform tenant has 1 account (seen 1h ago) + 1 payment (9999 cents) seeded.
    # Those must NOT appear in the headline numbers.
    assert stats["period_days"] == 30
    # active_customers: 2 (tenant A) + 1 (tenant B) = 3  (platform account excluded)
    assert stats["active_customers"] == 3
    # dau: a1 (2h ago) + b1 (5h ago) = 2  (platform account seen 1h ago must be excluded)
    assert stats["dau"] == 2
    # paid_customers: distinct accounts that paid in window = a1, a2, b1 = 3  (platform excluded)
    assert stats["paid_customers"] == 3
    # revenue: 500 + 700 + 900 = 2100  (platform payment of 9999 excluded)
    assert stats["revenue_cents"] == 2100
    # requests_by_kind summed globally (no platform requests seeded)
    assert stats["requests_by_kind"]["blueprint"] == 2
    assert stats["requests_by_kind"]["profile"] == 1

    # Global revenue == sum across tenants' per-tenant revenue
    per_tenant = {row["tenant_id"]: row for row in stats["per_tenant"]}
    assert sum(row["revenue_cents"] for row in stats["per_tenant"]) == stats["revenue_cents"]

    # per_tenant has an entry per non-platform tenant (tenant-a, tenant-b only)
    assert set(per_tenant.keys()) == {ta.id, tb.id}
    assert per_tenant[ta.id]["slug"] == "tenant-a"
    assert per_tenant[ta.id]["active_customers"] == 2
    assert per_tenant[ta.id]["paid_customers"] == 2
    assert per_tenant[ta.id]["revenue_cents"] == 1200
    assert per_tenant[tb.id]["slug"] == "tenant-b"
    assert per_tenant[tb.id]["active_customers"] == 1
    assert per_tenant[tb.id]["paid_customers"] == 1
    assert per_tenant[tb.id]["revenue_cents"] == 900

    # Confirm the platform tenant itself has no entry in per_tenant
    assert seeded_platform["default"].id not in per_tenant


async def test_platform_stats_funnel(session, seeded_platform):
    stats = await platform_stats(session, period_days=30)
    funnel = stats["funnel"]
    # 3 invites issued
    assert funnel["invites_issued"] == 3
    # invites_used: status="used" OR used_count>0 → INV-USED + INV-PARTIAL = 2
    assert funnel["invites_used"] == 2
    # active_tenants: tenant-a + tenant-b (default is platform) = 2
    assert funnel["active_tenants"] == 2


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sa_headers(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, None, True)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_route_superadmin_200(client, sa_headers, seeded_platform):
    r = await client.get("/admin/platform/stats?period_days=30", headers=sa_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["period_days"] == 30
    assert body["active_customers"] == 3
    assert body["paid_customers"] == 3
    assert body["revenue_cents"] == 2100
    assert body["requests_by_kind"]["blueprint"] == 2
    assert body["requests_by_kind"]["profile"] == 1

    per_tenant = {row["tenant_id"]: row for row in body["per_tenant"]}
    assert set(per_tenant.keys()) == {
        seeded_platform["tenant_a"].id,
        seeded_platform["tenant_b"].id,
    }
    assert per_tenant[seeded_platform["tenant_a"].id]["revenue_cents"] == 1200
    assert per_tenant[seeded_platform["tenant_b"].id]["revenue_cents"] == 900

    assert body["funnel"]["invites_issued"] == 3
    assert body["funnel"]["invites_used"] == 2
    assert body["funnel"]["active_tenants"] == 2


async def test_route_customer_403(client, customer_headers, seeded_platform):
    r = await client.get("/admin/platform/stats", headers=customer_headers)
    assert r.status_code == 403
