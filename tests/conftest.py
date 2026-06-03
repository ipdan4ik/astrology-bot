import asyncio
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


from quantuum.db.models import SQLModel  # noqa: E402

_DROP_ALL = (
    "DO $$ DECLARE r RECORD; BEGIN "
    "FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP "
    "EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE'; "
    "END LOOP; END $$"
)
_TRUNCATE_ALL = (
    "DO $$ DECLARE stmt TEXT; BEGIN "
    "SELECT 'TRUNCATE TABLE ' || string_agg(quote_ident(tablename), ', ') "
    "  || ' RESTART IDENTITY CASCADE' "
    "INTO stmt FROM pg_tables WHERE schemaname = 'public'; "
    "IF stmt IS NOT NULL THEN EXECUTE stmt; END IF; END $$"
)


def pytest_configure(config):
    """Give each xdist worker its own Postgres DB and Redis DB index.

    Worker processes have config.workerinput set by xdist. The controller process
    (which collects and distributes tests) does not — it does nothing here.
    Each worker gets:
      - Postgres: quantuum_test_gw0 / quantuum_test_gw1 / …
      - Redis:    DB 1 / 2 / … (DB 0 kept for non-parallel runs)
    The database is created synchronously before any async code runs.
    """
    worker_id = getattr(config, "workerinput", {}).get("workerid")
    if not worker_id:
        return

    # Redis: use DB index 1+ so workers don't collide with each other or
    # with a non-parallel run on DB 0.
    try:
        redis_idx = int(worker_id.replace("gw", "")) + 1
    except ValueError:
        redis_idx = 1
    base_redis = os.environ.get("REDIS_URL", "redis://172.30.0.3:6379/0")
    os.environ["REDIS_URL"] = base_redis.rsplit("/", 1)[0] + f"/{redis_idx}"

    # Postgres: create a fresh DB per worker.
    db_name = f"quantuum_test_{worker_id}"
    base_db = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://quantuum:quantuum@172.30.0.2:5432/quantuum_test",
    )
    prefix = base_db.rsplit("/", 1)[0]
    os.environ["DATABASE_URL"] = f"{prefix}/{db_name}"

    async def _ensure_db() -> None:
        import asyncpg  # available: asyncpg is a prod dependency

        conn = await asyncpg.connect(
            "postgresql://quantuum:quantuum@172.30.0.2:5432/postgres"
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db_name
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

    asyncio.run(_ensure_db())


@pytest_asyncio.fixture(scope="session")
async def engine():
    """One engine + schema for the whole test session (per xdist worker), built once.

    Per-test isolation is data-only — `_reset_state` TRUNCATEs every table before each
    test (fast DML, no per-test DDL). The whole suite runs on a single session-scoped
    event loop (see pyproject asyncio_*_loop_scope), so this one connection pool is
    reused across all tests. This replaced a per-test drop+create schema rebuild that
    made the suite ~5 min.
    """
    eng = create_async_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        await conn.execute(sqlalchemy.text(_DROP_ALL))
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _reset_state(engine):
    """Reset per-test state cheaply: TRUNCATE all tables (RESTART IDENTITY so ids reset
    like a fresh schema) and flush the test Redis (cached i18n strings / FSM state)."""
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text(_TRUNCATE_ALL))
    import quantuum.redis_client as rc

    await rc.get_redis().flushdb()
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _cleanup_singletons():
    """Dispose the app's lazily-created DB engine + Redis client at session end. They
    persist across tests (created once on the shared session loop) for speed; per-test
    isolation is data-only (handled by _reset_state)."""
    yield
    import quantuum.db.session as dbs
    import quantuum.redis_client as rc

    if dbs._engine is not None:
        await dbs._engine.dispose()
        dbs._engine = None
        dbs._sessionmaker = None
    if rc._redis is not None:
        await rc._redis.aclose()
        rc._redis = None


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


async def build_translator(session, tenant_id, *, lang: str | None = None):
    """Seed BASE_STRINGS + tenant languages and return a ready Translator.

    The default tenant lang is "ru" (matching production), so unless *lang* is
    given the returned Translator resolves Russian strings.
    """
    from quantuum.db.bootstrap import (
        ensure_base_strings,
        ensure_tenant_default_language,
    )
    from quantuum.i18n import Translator

    await ensure_base_strings(session)
    await ensure_tenant_default_language(session, tenant_id)
    return await Translator.build(
        session,
        tenant_id=tenant_id,
        preferred_lang=lang,
        tg_language_code=None,
    )
