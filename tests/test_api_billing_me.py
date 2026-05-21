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
