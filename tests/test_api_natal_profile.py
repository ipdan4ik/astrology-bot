import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg


@pytest_asyncio.fixture
async def auth_client(engine, session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1")
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


async def test_natal_profile_put_then_get(auth_client):
    payload = {
        "full_name": "Anna",
        "birth_date": "1980-06-24",
        "birth_time": "10:00:00",
        "birth_place": "Moscow",
        "latitude": "55.7558",
        "longitude": "37.6173",
        "timezone": "Europe/Moscow",
    }
    put = await auth_client.put("/v1/me/natal-profile", json=payload)
    assert put.status_code == 200

    get = await auth_client.get("/v1/me/natal-profile")
    assert get.status_code == 200
    assert get.json()["full_name"] == "Anna"


async def test_natal_profile_missing_returns_404(auth_client):
    assert (await auth_client.get("/v1/me/natal-profile")).status_code == 404
