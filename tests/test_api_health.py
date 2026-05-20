import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app


@pytest_asyncio.fixture
async def client(engine):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["db"] == "ok"
