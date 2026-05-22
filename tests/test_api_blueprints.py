import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg


@pytest_asyncio.fixture
async def auth_client(engine, session, default_tenant, monkeypatch):
    enqueued = []

    async def fake_enqueue(blueprint_id, chat_id=None, request_id=None):
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


async def test_create_blueprint_route_stores_resolved_lang(engine, session, default_tenant, monkeypatch):
    """Blueprint created via API must have lang equal to the account's preferred_lang."""
    from quantuum.api.app import create_app
    from quantuum.auth import jwt_tokens
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.bootstrap import ensure_base_strings, ensure_tenant_default_language
    from quantuum.domain.blueprints import get_blueprint
    from quantuum.tasks import enqueue as enqueue_mod

    # Ensure "fr" is an enabled tenant language so resolve_lang can return it.
    await ensure_base_strings(session)
    await ensure_tenant_default_language(session, default_tenant.id, extra_langs=("fr",))
    await session.commit()

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="99")
    acc.preferred_lang = "fr"
    session.add(acc)
    await session.commit()

    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id)

    async def fake_enqueue(blueprint_id, chat_id=None, request_id=None):
        pass

    monkeypatch.setattr(enqueue_mod, "enqueue_blueprint", fake_enqueue)

    app = create_app()
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        # Set up natal profile
        r = await client.put(
            "/v1/me/natal-profile",
            json={
                "full_name": "Test User",
                "birth_date": "1990-01-01",
                "birth_time": "12:00:00",
                "birth_place": "Paris",
                "latitude": "48.85",
                "longitude": "2.35",
                "timezone": "Europe/Paris",
            },
        )
        assert r.status_code == 200

        # Create blueprint
        r = await client.post("/v1/me/blueprints")
        assert r.status_code == 201
        bp_id = r.json()["id"]

    reloaded = await get_blueprint(session, bp_id)
    assert reloaded.lang == "fr"
