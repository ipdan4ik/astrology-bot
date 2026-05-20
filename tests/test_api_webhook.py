import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum import redis_client


@pytest_asyncio.fixture
async def client(engine):
    await redis_client.get_redis().flushdb()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await redis_client.get_redis().flushdb()


async def test_webhook_wrong_secret_404(client):
    r = await client.post("/tg/wrong-secret", json={"update_id": 1})
    assert r.status_code == 404


async def test_webhook_pushes_update(client):
    # WEBHOOK_SECRET_PATH is "test-secret-path" from conftest env.
    r = await client.post("/tg/test-secret-path", json={"update_id": 5, "message": {"text": "hi"}})
    assert r.status_code == 200
    item = await redis_client.pop_update(timeout=2)
    assert item["update_id"] == 5
