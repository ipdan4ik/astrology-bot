import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://quantuum:quantuum@172.30.0.2:5432/quantuum_test"
)
os.environ.setdefault("REDIS_URL", "redis://172.30.0.3:6379/0")
os.environ.setdefault("JWT_SIGNING_KEY", "test-secret")
os.environ.setdefault("WEBHOOK_SECRET_PATH", "test-secret-path")
os.environ.setdefault("BOT_TOKEN", "123:test")


@pytest_asyncio.fixture(autouse=True)
async def reset_redis():
    """Reset the global Redis singleton before each test so each test gets a fresh client
    bound to its own event loop."""
    import quantuum.redis_client as rc

    rc._redis = None
    yield
    if rc._redis is not None:
        await rc._redis.aclose()
        rc._redis = None

from quantuum.db.models import SQLModel  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def default_tenant(session):
    from quantuum.db.models import Tenant

    tenant = Tenant(slug="default", display_name="Quantuum")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant
