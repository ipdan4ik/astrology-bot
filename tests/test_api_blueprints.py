import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg


@pytest_asyncio.fixture
async def auth_client(engine, session, default_tenant, monkeypatch):
    enqueued = []

    async def fake_enqueue(blueprint_id, chat_id=None):
        enqueued.append((blueprint_id, chat_id))

    from quantuum.tasks import enqueue as enqueue_mod

    monkeypatch.setattr(enqueue_mod, "enqueue_blueprint", fake_enqueue)

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1")
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        c.enqueued = enqueued
        yield c


async def test_blueprint_requires_natal_profile(auth_client):
    r = await auth_client.post("/v1/me/blueprints")
    assert r.status_code == 409  # natal profile missing


async def test_blueprint_create_consumes_trial(auth_client):
    await auth_client.put(
        "/v1/me/natal-profile",
        json={
            "full_name": "Anna", "birth_date": "1980-06-24", "birth_time": "10:00:00",
            "birth_place": "Moscow", "latitude": "55.7", "longitude": "37.6",
            "timezone": "Europe/Moscow",
        },
    )
    r = await auth_client.post("/v1/me/blueprints")
    assert r.status_code == 201
    bp_id = r.json()["id"]
    assert auth_client.enqueued == [(bp_id, None)]

    # second one is blocked (trial used, no subscription/package)
    r2 = await auth_client.post("/v1/me/blueprints")
    assert r2.status_code == 402

    lst = await auth_client.get("/v1/me/blueprints")
    assert lst.status_code == 200
    assert len(lst.json()) == 1


async def test_blueprint_download(auth_client):
    await auth_client.put(
        "/v1/me/natal-profile",
        json={
            "full_name": "Anna", "birth_date": "1980-06-24", "birth_time": "10:00:00",
            "birth_place": "Moscow", "latitude": "55.7", "longitude": "37.6",
            "timezone": "Europe/Moscow",
        },
    )
    created = await auth_client.post("/v1/me/blueprints")
    bp_id = created.json()["id"]

    # No content yet -> 409
    dl_empty = await auth_client.get(f"/v1/me/blueprints/{bp_id}/download")
    assert dl_empty.status_code == 409
