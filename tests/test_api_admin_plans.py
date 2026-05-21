import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import Account, AccountIdentity


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
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()
    await session.refresh(acc)
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, None, True)}"}


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)}"}


async def test_create_and_list_subscription_plan(client, sa_headers):
    r = await client.post(
        "/admin/platform/plans/subscriptions",
        json={"slug": "annual", "name": "Annual", "period_days": 365, "price_cents": 2500},
        headers=sa_headers,
    )
    assert r.status_code == 201
    assert r.json()["slug"] == "annual"

    lst = await client.get("/admin/platform/plans/subscriptions", headers=sa_headers)
    assert lst.status_code == 200
    assert any(p["slug"] == "annual" for p in lst.json())


async def test_create_and_patch_package_plan(client, sa_headers):
    created = await client.post(
        "/admin/platform/plans/packages",
        json={"slug": "mega", "name": "Mega", "request_count": 100, "price_cents": 5000},
        headers=sa_headers,
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]

    patched = await client.patch(
        f"/admin/platform/plans/packages/{plan_id}",
        json={"price_cents": 4500, "active": False},
        headers=sa_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["price_cents"] == 4500
    assert patched.json()["active"] is False


async def test_customer_cannot_manage_plans(client, customer_headers):
    r = await client.get("/admin/platform/plans/subscriptions", headers=customer_headers)
    assert r.status_code == 403
