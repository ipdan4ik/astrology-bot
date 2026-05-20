import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.db.models import Tenant


@pytest_asyncio.fixture
async def client(engine):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Trigger lifespan startup explicitly.
        async with app.router.lifespan_context(app):
            yield c


async def test_startup_seeds_default_tenant(client, session):
    result = await session.execute(select(Tenant).where(Tenant.slug == "default"))
    assert result.scalar_one_or_none() is not None
