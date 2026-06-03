import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.bootstrap import ensure_global_plans
from quantuum.db.models import Account
from quantuum.domain.plans import list_subscription_plans
from quantuum.domain.providers import ensure_stars_provider


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_and_plan(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    await ensure_global_plans(session)
    await ensure_stars_provider(session, default_tenant.id)
    await session.commit()
    await session.refresh(acc)
    subs = await list_subscription_plans(session, tenant_id=default_tenant.id)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}, subs[0].id


async def test_post_subscription_returns_501(client, auth_and_plan):
    headers, plan_id = auth_and_plan
    r = await client.post("/v1/me/subscriptions", headers=headers, json={"plan_id": plan_id})
    assert r.status_code == 501


async def test_post_subscription_unknown_plan_404(client, auth_and_plan):
    headers, _ = auth_and_plan
    r = await client.post("/v1/me/subscriptions", headers=headers, json={"plan_id": 999999})
    assert r.status_code == 404


async def test_post_package_returns_501_or_404(client, auth_and_plan):
    headers, _ = auth_and_plan
    r = await client.post("/v1/me/packages", headers=headers, json={"plan_id": 999999})
    # unknown plan resolves to 404 before the provider; verify the route exists (not 405)
    assert r.status_code in (404, 501)


async def test_buy_subscription_rejects_other_tenant_plan(client, auth_and_plan, session):
    from quantuum.db.models import SubscriptionPlan, Tenant

    headers, _ = auth_and_plan
    other = Tenant(slug="idor-other", display_name="Other")
    session.add(other)
    await session.flush()
    foreign = SubscriptionPlan(
        tenant_id=other.id, slug="idor-foreign-sub", name="Foreign",
        period_days=30, price_cents=500, currency="XTR", active=True,
    )
    session.add(foreign)
    await session.commit()
    await session.refresh(foreign)

    r = await client.post(
        "/v1/me/subscriptions", headers=headers, json={"plan_id": foreign.id}
    )
    assert r.status_code == 404


async def test_buy_package_rejects_other_tenant_plan(client, auth_and_plan, session):
    from quantuum.db.models import PackagePlan, Tenant

    headers, _ = auth_and_plan
    other = Tenant(slug="idor-other-pkg", display_name="Other")
    session.add(other)
    await session.flush()
    foreign = PackagePlan(
        tenant_id=other.id, slug="idor-foreign-pkg", name="Foreign",
        request_count=10, price_cents=500, currency="XTR", active=True,
    )
    session.add(foreign)
    await session.commit()
    await session.refresh(foreign)

    r = await client.post(
        "/v1/me/packages", headers=headers, json={"plan_id": foreign.id}
    )
    assert r.status_code == 404
