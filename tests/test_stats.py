"""Tests for per-tenant real-time stats (Plan 5b, Task 12).

Route: GET /admin/tenants/{tenant_id}/stats?period_days=30
Domain: quantuum.domain.stats.tenant_stats
"""
from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountSubscription,
    Blueprint,
    NatalProfile,
    Payment,
    Request,
    SubscriptionPlan,
    Tenant,
)
from quantuum.domain.stats import tenant_stats
from quantuum.domain.tenants import grant_role


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(engine, seeded_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seeded_tenant(session):
    """Seed a tenant with precisely controlled data for stats assertions."""
    now = utcnow()

    tenant = Tenant(slug="stats-tenant", display_name="Stats Tenant")
    session.add(tenant)
    await session.flush()
    tid = tenant.id

    # --- 3 accounts ---
    # acc1: last_seen 12 hours ago → within 1d, 7d, 30d
    acc1 = Account(tenant_id=tid, last_seen_at=now - timedelta(hours=12))
    # acc2: last_seen 3 days ago → within 7d and 30d, NOT 1d
    acc2 = Account(tenant_id=tid, last_seen_at=now - timedelta(days=3))
    # acc3: last_seen 10 days ago → within 30d, NOT 1d or 7d
    acc3 = Account(tenant_id=tid, last_seen_at=now - timedelta(days=10))
    session.add_all([acc1, acc2, acc3])
    await session.flush()

    # acc1 is also the owner (needed for route auth test)
    await session.refresh(acc1)
    await session.refresh(acc2)
    await session.refresh(acc3)

    # --- payments ---
    # paid in-window (2 days ago) → counts toward revenue & paid_customers
    pay1 = Payment(
        tenant_id=tid,
        account_id=acc1.id,
        amount_cents=500,
        currency="XTR",
        status="paid",
        paid_at=now - timedelta(days=2),
    )
    # paid out-of-window (40 days ago) → does NOT count with period_days=30
    pay2 = Payment(
        tenant_id=tid,
        account_id=acc2.id,
        amount_cents=300,
        currency="XTR",
        status="paid",
        paid_at=now - timedelta(days=40),
    )
    # pending → never counts
    pay3 = Payment(
        tenant_id=tid,
        account_id=acc3.id,
        amount_cents=100,
        currency="XTR",
        status="pending",
    )
    session.add_all([pay1, pay2, pay3])
    await session.flush()

    # --- requests in window (created_at within 30 days) ---
    # blueprint x2
    req1 = Request(
        tenant_id=tid,
        account_id=acc1.id,
        kind="blueprint",
        created_at=now - timedelta(days=5),
    )
    req2 = Request(
        tenant_id=tid,
        account_id=acc2.id,
        kind="blueprint",
        created_at=now - timedelta(days=10),
    )
    # other kind x1
    req3 = Request(
        tenant_id=tid,
        account_id=acc3.id,
        kind="profile",
        created_at=now - timedelta(days=1),
    )
    # out-of-window request (should not count)
    req4 = Request(
        tenant_id=tid,
        account_id=acc1.id,
        kind="blueprint",
        created_at=now - timedelta(days=40),
    )
    session.add_all([req1, req2, req3, req4])
    await session.flush()

    # --- subscription plan + active subscription ---
    plan = SubscriptionPlan(
        tenant_id=tid,
        slug="monthly",
        name="Monthly",
        period_days=30,
        price_cents=250,
        currency="XTR",
    )
    session.add(plan)
    await session.flush()
    await session.refresh(plan)

    sub = AccountSubscription(
        tenant_id=tid,
        account_id=acc1.id,
        plan_id=plan.id,
        status="active",
        ends_at=now + timedelta(days=20),
    )
    session.add(sub)
    await session.flush()

    # --- blueprint with LLM tokens (in window) ---
    # Need a NatalProfile first as it's a FK requirement
    from datetime import date, time
    from decimal import Decimal

    np = NatalProfile(
        tenant_id=tid,
        account_id=acc1.id,
        full_name="Test User",
        birth_date=date(1990, 1, 1),
        birth_time=time(12, 0),
        birth_place="Moscow",
        latitude=Decimal("55.75"),
        longitude=Decimal("37.62"),
        timezone="Europe/Moscow",
    )
    session.add(np)
    await session.flush()
    await session.refresh(np)

    bp = Blueprint(
        tenant_id=tid,
        account_id=acc1.id,
        natal_profile_id=np.id,
        status="done",
        llm_tokens_in=10,
        llm_tokens_out=20,
        created_at=now - timedelta(days=5),
    )
    session.add(bp)
    await session.flush()

    await session.commit()
    await session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Domain-layer tests
# ---------------------------------------------------------------------------


async def test_stats_active_customers(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    # All 3 accounts have last_seen_at within the 30-day window
    assert stats["active_customers"] == 3


async def test_stats_paid_customers(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    # Only 1 payment was paid within the 30-day window (pay1, by acc1)
    assert stats["paid_customers"] == 1


async def test_stats_dau_wau_mau(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    # dau=1 (acc1 within 1 day), wau=2 (acc1+acc2 within 7 days), mau=3 (all within 30 days)
    assert stats["dau"] == 1
    assert stats["wau"] == 2
    assert stats["mau"] == 3


async def test_stats_requests_by_kind(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    rbk = stats["requests_by_kind"]
    # blueprint x2 in window, profile x1 in window; out-of-window blueprint not counted
    assert rbk["blueprint"] == 2
    assert rbk["profile"] == 1
    assert len(rbk) == 2


async def test_stats_revenue_cents(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    # Only pay1 (500) within 30 days; pay2 is 40 days ago; pay3 is pending
    assert stats["revenue_cents"] == 500


async def test_stats_mrr_cents(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    # 1 active subscription on plan with price_cents=250
    assert stats["mrr_cents"] == 250


async def test_stats_llm_tokens(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    assert stats["llm_tokens_in"] == 10
    assert stats["llm_tokens_out"] == 20


async def test_stats_period_days_key(session, seeded_tenant):
    stats = await tenant_stats(session, seeded_tenant.id, period_days=30)
    assert stats["period_days"] == 30


async def test_stats_custom_period(session, seeded_tenant):
    """With period_days=1, only in-window data within 1 day counts."""
    stats = await tenant_stats(session, seeded_tenant.id, period_days=1)
    # active_customers: last_seen within 1 day → only acc1 (12h ago)
    assert stats["active_customers"] == 1
    # revenue: pay1 was 2 days ago → 0
    assert stats["revenue_cents"] == 0
    # dau/wau/mau are FIXED windows (independent of period_days)
    assert stats["dau"] == 1
    assert stats["wau"] == 2
    assert stats["mau"] == 3


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner_headers(session, seeded_tenant):
    # Create owner account for seeded tenant
    acc = Account(tenant_id=seeded_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.flush()
    await grant_role(
        session,
        tenant_id=seeded_tenant.id,
        account_id=acc.id,
        role="owner",
        granted_by_account_id=None,
    )
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, seeded_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer_headers(session, seeded_tenant):
    acc = Account(tenant_id=seeded_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, seeded_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_route_owner_200(client, owner_headers, seeded_tenant):
    r = await client.get(
        f"/admin/tenants/{seeded_tenant.id}/stats?period_days=30",
        headers=owner_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["period_days"] == 30
    assert body["dau"] == 1
    assert body["wau"] == 2
    assert body["mau"] == 3
    assert body["active_customers"] == 3
    assert body["paid_customers"] == 1
    assert body["revenue_cents"] == 500
    assert body["mrr_cents"] == 250
    assert body["llm_tokens_in"] == 10
    assert body["llm_tokens_out"] == 20
    assert body["requests_by_kind"]["blueprint"] == 2
    assert body["requests_by_kind"]["profile"] == 1


async def test_route_customer_403(client, customer_headers, seeded_tenant):
    r = await client.get(
        f"/admin/tenants/{seeded_tenant.id}/stats",
        headers=customer_headers,
    )
    assert r.status_code == 403
