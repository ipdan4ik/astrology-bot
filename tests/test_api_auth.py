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


async def test_refresh_rotates_token_and_rejects_reuse(client, default_tenant, monkeypatch):
    async def fake_send(to_email, link):
        return None

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)
    token = await magic_link.create_magic_token("rot@example.com")
    r = await client.get(f"/auth/magic/consume?token={token}")
    assert r.status_code == 200
    old_refresh = r.json()["refresh_token"]

    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 200
    new_refresh = r2.json()["refresh_token"]
    assert new_refresh != old_refresh  # token was rotated

    # reusing the old (now consumed) refresh token is rejected
    r3 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r3.status_code == 401


async def test_superadmin_magic_login_issues_sa_token(client, session, monkeypatch):
    from quantuum.auth import jwt_tokens, magic_link
    from quantuum.db.models import Account, AccountIdentity

    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()

    async def fake_send(to_email, link):
        return None

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)
    token = await magic_link.create_magic_token("root@x.com")
    r = await client.get(f"/auth/magic/consume?token={token}")
    assert r.status_code == 200
    claims = jwt_tokens.verify_access_token(r.json()["access_token"])
    assert claims["sa"] is True
    assert claims["tid"] is None
