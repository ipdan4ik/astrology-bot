import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_consume_invalid_token(client):
    r = await client.get("/auth/magic/consume?token=bad")
    assert r.status_code == 400
