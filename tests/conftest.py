import os

import pytest_asyncio
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://quantuum:quantuum@172.30.0.2:5432/quantuum_test"
)
os.environ.setdefault("REDIS_URL", "redis://172.30.0.3:6379/0")
os.environ.setdefault("JWT_SIGNING_KEY", "test-secret")
os.environ.setdefault("WEBHOOK_SECRET_PATH", "test-secret-path")
os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("BOT_TOKEN_ENC_KEY", "wWyNAOxSSib9kfo4PeMJ6CX-ugqbCPhAp6kLVqHQL_0=")


@pytest_asyncio.fixture(autouse=True)
async def reset_redis():
    """Reset the global Redis singleton and flush the test DB before each test so each
    test gets a fresh client bound to its own event loop with no leftover keys."""
    import quantuum.redis_client as rc

    rc._redis = None
    # Flush the test Redis DB so cached i18n strings (and any other keys) from a
    # prior test don't bleed into the current one.
    await rc.get_redis().flushdb()
    yield
    if rc._redis is not None:
        await rc._redis.aclose()
        rc._redis = None


@pytest_asyncio.fixture(autouse=True)
async def reset_db_session():
    """Reset the global DB engine/sessionmaker singletons before each test so each test
    gets a fresh engine bound to its own event loop."""
    import quantuum.db.session as dbs

    dbs._engine = None
    dbs._sessionmaker = None
    yield
    if dbs._engine is not None:
        await dbs._engine.dispose()
        dbs._engine = None
        dbs._sessionmaker = None

from quantuum.db.models import SQLModel  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        # Use raw SQL to drop/create cleanly, handling ALTER constraints that may not exist
        await conn.execute(
            sqlalchemy.text(
                "DO $$ DECLARE r RECORD; BEGIN "
                "FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP "
                "EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE'; "
                "END LOOP; END $$"
            )
        )
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
