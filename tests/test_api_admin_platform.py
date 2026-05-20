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


async def test_create_and_list_invite(client, sa_headers):
    r = await client.post(
        "/admin/platform/invites",
        json={"tier": "basic", "max_uses": 2},
        headers=sa_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["code"]
    assert body["deeplink"].endswith(body["code"])
    assert body["tier"] == "basic"

    lst = await client.get("/admin/platform/invites", headers=sa_headers)
    assert lst.status_code == 200
    assert any(i["code"] == body["code"] for i in lst.json())


async def test_revoke_invite(client, sa_headers):
    created = await client.post("/admin/platform/invites", json={}, headers=sa_headers)
    invite_id = created.json()["id"]
    r = await client.post(f"/admin/platform/invites/{invite_id}/revoke", headers=sa_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


async def test_list_tenants(client, sa_headers, default_tenant):
    r = await client.get("/admin/platform/tenants", headers=sa_headers)
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()}
    assert "default" in slugs


async def test_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/invites", headers=customer_headers)
    assert r.status_code == 403
