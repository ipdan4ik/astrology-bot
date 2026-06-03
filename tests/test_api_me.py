import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_me_requires_auth(client):
    assert (await client.get("/v1/me")).status_code == 401


async def test_me_returns_account(client, session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1")
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id)
    r = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"account_id": acc.id, "tenant_id": default_tenant.id}


async def _auth_headers(session, default_tenant, tg="pg1"):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id=tg)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id)
    return acc, {"Authorization": f"Bearer {token}"}


async def test_qa_list_rejects_oversized_limit(client, session, default_tenant):
    _, headers = await _auth_headers(session, default_tenant, tg="qa-lim")
    resp = await client.get("/v1/me/qa?limit=10000", headers=headers)
    assert resp.status_code == 422


async def test_payments_list_accepts_limit(client, session, default_tenant):
    from quantuum.db.models import Payment

    acc, headers = await _auth_headers(session, default_tenant, tg="pay-lim")
    for _ in range(3):
        session.add(Payment(
            tenant_id=default_tenant.id, account_id=acc.id, amount_cents=100,
        ))
    await session.commit()

    resp = await client.get("/v1/me/payments?limit=2", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # limit honored
