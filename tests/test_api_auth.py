import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import magic_link


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_consume_invalid_token(client):
    r = await client.get("/auth/magic/consume?token=bad")
    assert r.status_code == 400


async def test_magic_login_flow(client, default_tenant, monkeypatch):
    async def fake_send(to_email, link):
        return None

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)

    r1 = await client.post("/auth/magic/request", json={"email": "u@example.com"})
    assert r1.status_code == 200
    assert r1.json()["sent"] is True

    token = await magic_link.create_magic_token("u@example.com")
    r2 = await client.get(f"/auth/magic/consume?token={token}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["access_token"]
    assert body["refresh_token"]

    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["tenant_id"] == default_tenant.id
