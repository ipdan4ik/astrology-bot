import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.bootstrap import ensure_global_plans
from quantuum.db.models import Account, AccountBalance


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id, package_credits=3))
    await ensure_global_plans(session)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_get_balance(client, auth):
    r = await client.get("/v1/me/balance", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["package_credits"] == 3
    assert body["free_trial_used"] is False


async def test_get_plans(client, auth):
    r = await client.get("/v1/me/plans", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert {p["slug"] for p in body["subscriptions"]} == {"monthly"}
    assert {p["slug"] for p in body["packages"]} == {"pack_small", "pack_large"}


async def test_get_subscriptions_and_payments(client, auth, session, default_tenant):
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import AccountSubscription, Payment, SubscriptionPlan

    # find the account id from the token-bound balance row created in the auth fixture
    from sqlmodel import select
    acc_id = (await session.execute(select(Account.id))).scalars().first()

    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc_id, plan_id=plan.id,
        status="active", started_at=utcnow(), ends_at=utcnow(),
    ))
    session.add(Payment(
        tenant_id=default_tenant.id, account_id=acc_id, amount_cents=250,
        currency="XTR", status="paid",
    ))
    await session.commit()

    rs = await client.get("/v1/me/subscriptions", headers=auth)
    assert rs.status_code == 200
    assert any(s["status"] == "active" for s in rs.json())

    rp = await client.get("/v1/me/payments", headers=auth)
    assert rp.status_code == 200
    assert any(p["amount_cents"] == 250 and p["status"] == "paid" for p in rp.json())
