# Foundation + Single-Tenant Bot MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable end-to-end astrology Telegram bot that collects natal data and returns a (mocked) Blueprint document, with the data layer, auth, and process topology already shaped for the full multi-tenant platform.

**Architecture:** Three processes (FastAPI `api`, aiogram `bot-worker`, arq `task-worker`) over shared Postgres + Redis, in docker-compose. This plan is **single-tenant**: one `tenants` row is seeded and every domain row carries its `tenant_id`, but there is no tenant resolution, roles, master bot, or onboarding yet (those arrive in Plan 2). The Blueprint generation pipeline is real (request → quota → enqueue → worker → deliver) but the calculator + LLM are replaced by a fixed mock markdown.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3.x, SQLModel (SQLAlchemy 2 async + asyncpg), Alembic, Redis 7, arq, structlog, pytest + pytest-asyncio + httpx, uv, Docker Compose.

---

## Context

Spec: `docs/superpowers/specs/2026-05-19-quantuum-bot-platform-design.md`.

**In scope for this plan:**
- Project skeleton, dependency management (uv), docker-compose, Dockerfile.
- DB layer: SQLModel models for `tenants`, `accounts`, `account_identities`, `account_refresh_tokens`, `natal_profiles`, `blueprints`, `requests`, `account_balance`. Alembic migrations.
- Settings (Pydantic Settings), structlog logging, request-id propagation.
- Auth: email **magic link** only (issue + consume), JWT access + refresh, `current_account` dependency.
- Public API: `/healthz`, `/readyz`, `/v1/me`, `/v1/me/natal-profile` (GET/PUT), `/v1/me/blueprints` (GET/POST), `/v1/me/blueprints/{id}`, `/v1/me/blueprints/{id}/download`.
- Telegram webhook receiver that pushes updates to a Redis queue.
- bot-worker: aiogram dispatcher, queue consumer, `/start`, natal-profile onboarding FSM, `/blueprint` command.
- task-worker: arq, `blueprint_generate` task producing the mock Blueprint and delivering it as a `.md` document.
- Quota: `account_balance.free_trial_used` + `consume_quota` (trial path only; paid paths raise `InsufficientFunds`).

**Explicitly OUT of scope (later plans):**
- Multi-tenancy logic (resolution middleware, `tenant_roles`, `tenant_bots`), master bot, `tenant_invites`, provisioning, polling transport (Plan 2).
- Payments, plans, subscriptions, packages, payment callbacks (Plan 3).
- Real astrology engine port + real LLM (Plan 4).
- i18n tables/resolver, admin API, stats, audit_log (Plan 5).
- Telegram OAuth, account linking/merge (Plan 2+).

**Single-tenant convention:** A helper `get_default_tenant_id(session)` returns the id of the seeded `tenants` row (`slug="default"`). All domain writes use it. Plan 2 renames this row to the platform tenant and replaces the helper with real resolution.

---

## File Structure

```
quantuum-bot/
  pyproject.toml                      # deps, tool config (ruff, pytest)
  uv.lock                             # generated
  Dockerfile                          # single image, CMD overridden per service
  docker-compose.yml                  # postgres, redis, migration, api, bot-worker, task-worker
  docker-compose.test.yml             # postgres-test, redis-test for the test suite
  .env.example                        # documented env vars
  alembic.ini
  alembic/
    env.py                            # async Alembic env, imports SQLModel metadata
    versions/                         # migration scripts
  src/quantuum/
    __init__.py                       # __version__
    settings.py                       # Settings (Pydantic BaseSettings)
    logging_setup.py                  # structlog config + request-id contextvar
    redis_client.py                   # redis pool + update-queue push/pop helpers
    common/
      __init__.py
      datetime.py                     # utcnow()
      ids.py                          # random url-safe token generator
      exceptions.py                   # domain exceptions (InsufficientFunds, NotFound, ...)
    db/
      __init__.py
      models.py                       # all SQLModel table models
      session.py                      # async engine + session factory + get_session dep
      bootstrap.py                    # seed default tenant
    auth/
      __init__.py
      jwt_tokens.py                   # issue/verify access + refresh tokens
      magic_link.py                   # create/consume magic-link tokens, email sender
      identity.py                     # find_or_create_account_by_identity
    domain/
      __init__.py
      tenants.py                      # get_default_tenant_id
      accounts.py                     # touch_last_seen, get_account
      natal_profiles.py               # get / upsert natal profile
      quota.py                        # consume_quota / refund_quota
      blueprints.py                   # create / load / status transitions
      requests.py                     # create / complete / fail request log
      mock_blueprint.py               # MOCK_BLUEPRINT_MD content
    api/
      __init__.py
      app.py                          # FastAPI factory + middleware wiring
      deps.py                         # current_account dependency, get_session
      schemas.py                      # Pydantic request/response models
      routes/
        __init__.py
        health.py                     # /healthz, /readyz
        auth.py                       # /auth/magic/*, /auth/refresh, /auth/logout
        me.py                         # /v1/me, natal-profile, blueprints
        webhook.py                    # /tg/{secret_path}
    bot/
      __init__.py
      app.py                          # Bot + Dispatcher factory (MemoryStorage)
      runner.py                       # bot-worker entrypoint: consume queue → feed dispatcher
      middleware/
        __init__.py
        account.py                    # AccountMiddleware: from_user.id → account
      handlers/
        __init__.py
        start.py                      # /start
        onboarding.py                 # natal-data FSM
        blueprint.py                  # /blueprint
    tasks/
      __init__.py
      worker.py                       # arq WorkerSettings + ctx setup
      blueprint.py                    # blueprint_generate task
  tests/
    __init__.py
    conftest.py                       # event loop, db engine, session, http client, redis fixtures
    test_settings.py
    test_db_models.py
    test_jwt_tokens.py
    test_magic_link.py
    test_identity.py
    test_quota.py
    test_blueprints_service.py
    test_api_health.py
    test_api_auth.py
    test_api_me.py
    test_api_natal_profile.py
    test_api_blueprints.py
    test_api_webhook.py
    test_task_blueprint.py
    test_bot_onboarding.py
    test_bot_blueprint.py
```

**Module signatures locked here (used consistently across tasks):**

```python
# settings.py
class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_signing_key: str
    jwt_access_ttl_seconds: int = 3600
    jwt_refresh_ttl_seconds: int = 2_592_000  # 30 days
    bot_token: str = ""
    webhook_secret_path: str = ""
    api_host: str = "http://localhost:8000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@quantuum.example"
    default_tenant_slug: str = "default"
    default_tenant_name: str = "Quantuum"
    magic_link_ttl_seconds: int = 900
    log_json: bool = True

# common/exceptions.py
class DomainError(Exception): ...
class NotFoundError(DomainError): ...
class InsufficientFundsError(DomainError): ...
class NatalProfileMissingError(DomainError): ...

# domain/quota.py
async def consume_quota(session, account_id: int, kind: str) -> str: ...   # returns "trial"|"subscription"|"package"
async def refund_quota(session, request_id: int) -> None: ...

# domain/blueprints.py
async def create_blueprint(session, *, tenant_id: int, account_id: int, natal_profile_id: int) -> Blueprint: ...
async def set_status(session, blueprint_id: int, status: str, **fields) -> None: ...
async def get_blueprint(session, blueprint_id: int) -> Blueprint: ...

# auth/identity.py
async def find_or_create_account_by_email(session, *, tenant_id: int, email: str) -> Account: ...
async def find_or_create_account_by_tg(session, *, tenant_id: int, tg_user_id: str) -> Account: ...

# auth/jwt_tokens.py
def issue_access_token(account_id: int, tenant_id: int) -> str: ...
def verify_access_token(token: str) -> dict: ...          # returns claims, raises jwt errors
async def issue_refresh_token(session, account_id: int) -> str: ...
async def consume_refresh_token(session, token: str) -> Account: ...
async def revoke_refresh_token(session, token: str) -> None: ...
```

---

## Task 1: Project skeleton + dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `src/quantuum/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "quantuum-bot"
version = "0.1.0"
description = "Multi-tenant astrology Telegram bot platform"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "aiogram>=3.13",
    "sqlmodel>=0.0.22",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "redis>=5.2",
    "arq>=0.26",
    "structlog>=24.4",
    "pydantic-settings>=2.6",
    "pyjwt>=2.10",
    "aiosmtplib>=3.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/quantuum"]
```

- [ ] **Step 2: Create package marker files**

`src/quantuum/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`:
```python
```

- [ ] **Step 3: Install toolchain and sync dependencies**

Run: `command -v uv || pip install uv` then `uv sync`
Expected: creates `.venv/` and `uv.lock`, exits 0.

- [ ] **Step 4: Verify the package imports**

Run: `uv run python -c "import quantuum; print(quantuum.__version__)"`
Expected: prints `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/quantuum/__init__.py tests/__init__.py
git commit -m "chore: project skeleton and dependencies"
```

---

## Task 2: Settings module

**Files:**
- Create: `src/quantuum/settings.py`
- Create: `.env.example`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

`tests/test_settings.py`:
```python
import os

from quantuum.settings import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SIGNING_KEY", "secret")
    s = Settings()
    assert s.database_url.endswith("/db")
    assert s.jwt_access_ttl_seconds == 3600
    assert s.default_tenant_slug == "default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.settings'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/settings.py`:
```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_signing_key: str
    jwt_access_ttl_seconds: int = 3600
    jwt_refresh_ttl_seconds: int = 2_592_000
    bot_token: str = ""
    webhook_secret_path: str = ""
    api_host: str = "http://localhost:8000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@quantuum.example"
    default_tenant_slug: str = "default"
    default_tenant_name: str = "Quantuum"
    magic_link_ttl_seconds: int = 900
    log_json: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Create `.env.example`**

```bash
DATABASE_URL=postgresql+asyncpg://quantuum:quantuum@postgres:5432/quantuum
REDIS_URL=redis://redis:6379/0
JWT_SIGNING_KEY=change-me-in-prod
BOT_TOKEN=
WEBHOOK_SECRET_PATH=
API_HOST=http://localhost:8000
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@quantuum.example
LOG_JSON=true
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/settings.py .env.example tests/test_settings.py
git commit -m "feat: settings module"
```

---

## Task 3: Common utilities

**Files:**
- Create: `src/quantuum/common/__init__.py`, `datetime.py`, `ids.py`, `exceptions.py`

- [ ] **Step 1: Create the utility modules**

`src/quantuum/common/__init__.py`:
```python
```

`src/quantuum/common/datetime.py`:
```python
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
```

`src/quantuum/common/ids.py`:
```python
import secrets


def url_safe_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
```

`src/quantuum/common/exceptions.py`:
```python
class DomainError(Exception):
    """Base class for domain-level errors."""


class NotFoundError(DomainError):
    pass


class InsufficientFundsError(DomainError):
    pass


class NatalProfileMissingError(DomainError):
    pass
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from quantuum.common.datetime import utcnow; from quantuum.common.ids import url_safe_token; from quantuum.common.exceptions import InsufficientFundsError; print(utcnow(), len(url_safe_token()) > 0)"`
Expected: prints a timestamp and `True`

- [ ] **Step 3: Commit**

```bash
git add src/quantuum/common/
git commit -m "feat: common utilities (datetime, ids, exceptions)"
```

---

## Task 4: SQLModel models

**Files:**
- Create: `src/quantuum/db/__init__.py`, `src/quantuum/db/models.py`
- Test: `tests/test_db_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_db_models.py`:
```python
from quantuum.db import models


def test_all_tables_registered():
    names = set(models.SQLModel.metadata.tables.keys())
    assert {
        "tenants",
        "accounts",
        "account_identities",
        "account_refresh_tokens",
        "natal_profiles",
        "blueprints",
        "requests",
        "account_balance",
    } <= names


def test_blueprint_defaults():
    bp = models.Blueprint(tenant_id=1, account_id=1, natal_profile_id=1)
    assert bp.status == "pending"
    assert bp.calc_md is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.db'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/db/__init__.py`:
```python
```

`src/quantuum/db/models.py`:
```python
from datetime import date, datetime, time
from decimal import Decimal

from sqlmodel import Field, SQLModel

from quantuum.common.datetime import utcnow


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    display_name: str
    status: str = "active"  # active|suspended|archived
    created_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    status: str = "active"  # active|disabled
    preferred_lang: str | None = None
    last_seen_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AccountIdentity(SQLModel, table=True):
    __tablename__ = "account_identities"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    provider: str  # tg_chat|magic_link
    provider_user_id: str | None = Field(default=None, index=True)
    email: str | None = Field(default=None, index=True)
    verified_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class AccountRefreshToken(SQLModel, table=True):
    __tablename__ = "account_refresh_tokens"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    token_hash: str = Field(index=True)
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class NatalProfile(SQLModel, table=True):
    __tablename__ = "natal_profiles"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", unique=True, index=True)
    full_name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    for_year: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Blueprint(SQLModel, table=True):
    __tablename__ = "blueprints"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    status: str = "pending"  # pending|calculating|generating|done|failed
    calc_md: str | None = None
    llm_md: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class Request(SQLModel, table=True):
    __tablename__ = "requests"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    kind: str  # blueprint
    reference_id: int | None = None
    reference_type: str | None = None
    status: str = "pending"  # pending|done|failed|refunded
    cost_units: int = 1
    charged_against: str | None = None  # trial|subscription|package|none
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class AccountBalance(SQLModel, table=True):
    __tablename__ = "account_balance"

    account_id: int = Field(foreign_key="accounts.id", primary_key=True)
    free_trial_used: bool = False
    subscription_active_until: datetime | None = None
    package_credits: int = 0
    updated_at: datetime = Field(default_factory=utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/db/__init__.py src/quantuum/db/models.py tests/test_db_models.py
git commit -m "feat: SQLModel data models"
```

---

## Task 5: Async DB session factory

**Files:**
- Create: `src/quantuum/db/session.py`

- [ ] **Step 1: Write the implementation**

`src/quantuum/db/session.py`:
```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantuum.settings import get_settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from quantuum.db.session import get_sessionmaker; print(callable(get_sessionmaker))"`
Expected: prints `True`

- [ ] **Step 3: Commit**

```bash
git add src/quantuum/db/session.py
git commit -m "feat: async DB session factory"
```

---

## Task 6: Docker Compose + Dockerfile + test compose

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# Default command runs the API; compose overrides per service.
CMD ["uv", "run", "uvicorn", "quantuum.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: quantuum
      POSTGRES_PASSWORD: quantuum
      POSTGRES_DB: quantuum
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U quantuum"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  migration:
    build: .
    command: uv run alembic upgrade head
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build: .
    command: uv run uvicorn quantuum.api.app:create_app --factory --host 0.0.0.0 --port 8000
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      migration:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

  bot-worker:
    build: .
    command: uv run python -m quantuum.bot.runner
    env_file: .env
    depends_on:
      migration:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

  task-worker:
    build: .
    command: uv run arq quantuum.tasks.worker.WorkerSettings
    env_file: .env
    depends_on:
      migration:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

volumes:
  postgres-data:
  redis-data:
```

- [ ] **Step 3: Create `docker-compose.test.yml`**

```yaml
services:
  postgres-test:
    image: postgres:16
    environment:
      POSTGRES_USER: quantuum
      POSTGRES_PASSWORD: quantuum
      POSTGRES_DB: quantuum_test
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U quantuum"]
      interval: 3s
      timeout: 3s
      retries: 10

  redis-test:
    image: redis:7
    ports:
      - "6380:6379"
```

- [ ] **Step 4: Bring up test infra and verify**

Run: `docker compose -f docker-compose.test.yml up -d && sleep 5 && docker compose -f docker-compose.test.yml ps`
Expected: `postgres-test` and `redis-test` are running.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml docker-compose.test.yml
git commit -m "chore: docker-compose and Dockerfile"
```

---

## Task 7: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/versions/` (generated)

- [ ] **Step 1: Create `alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = src
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 2: Create `alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from quantuum.db import models  # noqa: F401  (registers tables)
from quantuum.db.models import SQLModel
from quantuum.settings import get_settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: Generate the initial migration**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://quantuum:quantuum@localhost:5433/quantuum_test \
REDIS_URL=redis://localhost:6380/0 JWT_SIGNING_KEY=test \
uv run alembic revision --autogenerate -m "initial schema"
```
Expected: a new file appears under `alembic/versions/` containing `create_table` for all 8 tables.

- [ ] **Step 4: Apply the migration and verify**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://quantuum:quantuum@localhost:5433/quantuum_test \
REDIS_URL=redis://localhost:6380/0 JWT_SIGNING_KEY=test \
uv run alembic upgrade head
```
Expected: `INFO ... Running upgrade -> <rev>, initial schema`, exits 0.

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic/env.py alembic/versions/
git commit -m "feat: alembic setup and initial schema migration"
```

---

## Task 8: Test fixtures (conftest)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://quantuum:quantuum@localhost:5433/quantuum_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("JWT_SIGNING_KEY", "test-secret")
os.environ.setdefault("WEBHOOK_SECRET_PATH", "test-secret-path")
os.environ.setdefault("BOT_TOKEN", "123:test")

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
```

- [ ] **Step 2: Run the existing model test through the new fixtures path**

Run: `uv run pytest tests/test_db_models.py -v`
Expected: PASS (conftest import does not break collection).

- [ ] **Step 3: Add a fixture sanity test**

Append to `tests/test_db_models.py`:
```python
async def test_default_tenant_fixture(default_tenant):
    assert default_tenant.id is not None
    assert default_tenant.slug == "default"
```

- [ ] **Step 4: Run it**

Run: `uv run pytest tests/test_db_models.py::test_default_tenant_fixture -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_db_models.py
git commit -m "test: async db fixtures"
```

---

## Task 9: Bootstrap (seed default tenant) + tenants domain helper

**Files:**
- Create: `src/quantuum/db/bootstrap.py`, `src/quantuum/domain/__init__.py`, `src/quantuum/domain/tenants.py`
- Test: add to `tests/test_db_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db_models.py`:
```python
async def test_bootstrap_seeds_default_tenant(session):
    from quantuum.db.bootstrap import ensure_default_tenant
    from quantuum.domain.tenants import get_default_tenant_id

    t1 = await ensure_default_tenant(session)
    t2 = await ensure_default_tenant(session)  # idempotent
    assert t1.id == t2.id
    assert await get_default_tenant_id(session) == t1.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_models.py::test_bootstrap_seeds_default_tenant -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.db.bootstrap'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/domain/__init__.py`:
```python
```

`src/quantuum/db/bootstrap.py`:
```python
from sqlmodel import select

from quantuum.db.models import Tenant
from quantuum.settings import get_settings


async def ensure_default_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=settings.default_tenant_slug, display_name=settings.default_tenant_name)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant
```

`src/quantuum/domain/tenants.py`:
```python
from sqlmodel import select

from quantuum.db.models import Tenant
from quantuum.settings import get_settings


async def get_default_tenant_id(session) -> int:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one()
    return tenant.id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db_models.py::test_bootstrap_seeds_default_tenant -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/db/bootstrap.py src/quantuum/domain/__init__.py src/quantuum/domain/tenants.py tests/test_db_models.py
git commit -m "feat: default tenant bootstrap and helper"
```

---

## Task 10: JWT tokens

**Files:**
- Create: `src/quantuum/auth/__init__.py`, `src/quantuum/auth/jwt_tokens.py`
- Test: `tests/test_jwt_tokens.py`

- [ ] **Step 1: Write the failing test**

`tests/test_jwt_tokens.py`:
```python
import hashlib

import pytest

from quantuum.auth import jwt_tokens
from quantuum.common.exceptions import NotFoundError


def test_access_token_roundtrip():
    token = jwt_tokens.issue_access_token(account_id=7, tenant_id=3)
    claims = jwt_tokens.verify_access_token(token)
    assert claims["sub"] == "7"
    assert claims["tid"] == 3


async def test_refresh_token_consume(session, default_tenant):
    from quantuum.db.models import Account

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    token = await jwt_tokens.issue_refresh_token(session, acc.id)
    consumed = await jwt_tokens.consume_refresh_token(session, token)
    assert consumed.id == acc.id


async def test_refresh_token_revoked(session, default_tenant):
    from quantuum.db.models import Account

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    token = await jwt_tokens.issue_refresh_token(session, acc.id)
    await jwt_tokens.revoke_refresh_token(session, token)
    with pytest.raises(NotFoundError):
        await jwt_tokens.consume_refresh_token(session, token)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jwt_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.auth'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/auth/__init__.py`:
```python
```

`src/quantuum/auth/jwt_tokens.py`:
```python
import hashlib
from datetime import timedelta

import jwt
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.common.ids import url_safe_token
from quantuum.db.models import Account, AccountRefreshToken
from quantuum.settings import get_settings

_ALG = "HS256"


def issue_access_token(account_id: int, tenant_id: int) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": str(account_id),
        "tid": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=_ALG)


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_signing_key, algorithms=[_ALG])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_refresh_token(session, account_id: int) -> str:
    settings = get_settings()
    token = url_safe_token()
    row = AccountRefreshToken(
        account_id=account_id,
        token_hash=_hash(token),
        expires_at=utcnow() + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
    )
    session.add(row)
    await session.commit()
    return token


async def _load_active(session, token: str) -> AccountRefreshToken:
    result = await session.execute(
        select(AccountRefreshToken).where(AccountRefreshToken.token_hash == _hash(token))
    )
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        raise NotFoundError("refresh token invalid")
    return row


async def consume_refresh_token(session, token: str) -> Account:
    row = await _load_active(session, token)
    account = await session.get(Account, row.account_id)
    if account is None:
        raise NotFoundError("account not found")
    return account


async def revoke_refresh_token(session, token: str) -> None:
    result = await session.execute(
        select(AccountRefreshToken).where(AccountRefreshToken.token_hash == _hash(token))
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.revoked_at = utcnow()
        session.add(row)
        await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_jwt_tokens.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/auth/__init__.py src/quantuum/auth/jwt_tokens.py tests/test_jwt_tokens.py
git commit -m "feat: JWT access and refresh tokens"
```

---

## Task 11: Identity resolution

**Files:**
- Create: `src/quantuum/auth/identity.py`, `src/quantuum/domain/accounts.py`
- Test: `tests/test_identity.py`

- [ ] **Step 1: Write the failing test**

`tests/test_identity.py`:
```python
from quantuum.auth.identity import (
    find_or_create_account_by_email,
    find_or_create_account_by_tg,
)


async def test_email_identity_idempotent(session, default_tenant):
    a1 = await find_or_create_account_by_email(
        session, tenant_id=default_tenant.id, email="x@example.com"
    )
    a2 = await find_or_create_account_by_email(
        session, tenant_id=default_tenant.id, email="x@example.com"
    )
    assert a1.id == a2.id


async def test_tg_identity_creates_balance(session, default_tenant):
    from quantuum.db.models import AccountBalance

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="555"
    )
    bal = await session.get(AccountBalance, acc.id)
    assert bal is not None
    assert bal.free_trial_used is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.auth.identity'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/auth/identity.py`:
```python
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountBalance, AccountIdentity


async def _ensure_balance(session, account_id: int) -> None:
    existing = await session.get(AccountBalance, account_id)
    if existing is None:
        session.add(AccountBalance(account_id=account_id))


async def _create_account(session, tenant_id: int) -> Account:
    account = Account(tenant_id=tenant_id)
    session.add(account)
    await session.flush()
    await _ensure_balance(session, account.id)
    return account


async def find_or_create_account_by_email(session, *, tenant_id: int, email: str) -> Account:
    result = await session.execute(
        select(AccountIdentity)
        .join(Account, Account.id == AccountIdentity.account_id)
        .where(
            AccountIdentity.provider == "magic_link",
            AccountIdentity.email == email,
            Account.tenant_id == tenant_id,
        )
    )
    identity = result.scalar_one_or_none()
    if identity is not None:
        return await session.get(Account, identity.account_id)

    account = await _create_account(session, tenant_id)
    session.add(
        AccountIdentity(
            account_id=account.id, provider="magic_link", email=email, verified_at=utcnow()
        )
    )
    await session.commit()
    await session.refresh(account)
    return account


async def find_or_create_account_by_tg(session, *, tenant_id: int, tg_user_id: str) -> Account:
    result = await session.execute(
        select(AccountIdentity)
        .join(Account, Account.id == AccountIdentity.account_id)
        .where(
            AccountIdentity.provider == "tg_chat",
            AccountIdentity.provider_user_id == tg_user_id,
            Account.tenant_id == tenant_id,
        )
    )
    identity = result.scalar_one_or_none()
    if identity is not None:
        return await session.get(Account, identity.account_id)

    account = await _create_account(session, tenant_id)
    session.add(
        AccountIdentity(
            account_id=account.id,
            provider="tg_chat",
            provider_user_id=tg_user_id,
            verified_at=utcnow(),
        )
    )
    await session.commit()
    await session.refresh(account)
    return account
```

`src/quantuum/domain/accounts.py`:
```python
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account


async def touch_last_seen(session, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is not None:
        account.last_seen_at = utcnow()
        session.add(account)
        await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_identity.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/auth/identity.py src/quantuum/domain/accounts.py tests/test_identity.py
git commit -m "feat: account identity resolution"
```

---

## Task 12: Quota service (trial path)

**Files:**
- Create: `src/quantuum/domain/quota.py`, `src/quantuum/domain/requests.py`
- Test: `tests/test_quota.py`

- [ ] **Step 1: Write the failing test**

`tests/test_quota.py`:
```python
import pytest

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.domain.quota import consume_quota, refund_quota


async def _make_account(session, tenant_id):
    from quantuum.auth.identity import find_or_create_account_by_tg

    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="1")


async def test_first_blueprint_uses_trial(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"


async def test_second_blueprint_blocked(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint")


async def test_refund_restores_trial(session, default_tenant):
    from quantuum.db.models import Request

    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint", charged_against="trial"
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)

    # trial available again
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_quota.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.domain.quota'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/domain/quota.py`:
```python
from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, Request


async def consume_quota(session, account_id: int, kind: str) -> str:
    balance = await session.get(AccountBalance, account_id, with_for_update=True)
    if balance is None:
        balance = AccountBalance(account_id=account_id)
        session.add(balance)

    if not balance.free_trial_used and kind == "blueprint":
        balance.free_trial_used = True
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "trial"

    if balance.subscription_active_until and balance.subscription_active_until > utcnow():
        return "subscription"

    if balance.package_credits >= 1:
        balance.package_credits -= 1
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "package"

    raise InsufficientFundsError("no quota available")


async def refund_quota(session, request_id: int) -> None:
    request = await session.get(Request, request_id)
    if request is None or request.charged_against in (None, "none"):
        return

    balance = await session.get(AccountBalance, request.account_id, with_for_update=True)
    if balance is not None:
        if request.charged_against == "trial":
            balance.free_trial_used = False
        elif request.charged_against == "package":
            balance.package_credits += 1
        balance.updated_at = utcnow()
        session.add(balance)

    request.charged_against = "none"
    request.status = "refunded"
    session.add(request)
    await session.commit()
```

`src/quantuum/domain/requests.py`:
```python
from quantuum.common.datetime import utcnow
from quantuum.db.models import Request


async def create_request(
    session, *, tenant_id: int, account_id: int, kind: str, charged_against: str
) -> Request:
    request = Request(
        tenant_id=tenant_id,
        account_id=account_id,
        kind=kind,
        charged_against=charged_against,
        status="pending",
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def complete_request(session, request_id: int, *, reference_id: int, reference_type: str) -> None:
    request = await session.get(Request, request_id)
    if request is not None:
        request.status = "done"
        request.reference_id = reference_id
        request.reference_type = reference_type
        request.completed_at = utcnow()
        session.add(request)
        await session.commit()


async def fail_request(session, request_id: int) -> None:
    request = await session.get(Request, request_id)
    if request is not None:
        request.status = "failed"
        request.completed_at = utcnow()
        session.add(request)
        await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_quota.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/quota.py src/quantuum/domain/requests.py tests/test_quota.py
git commit -m "feat: quota consume/refund and request log"
```

---

## Task 13: Mock blueprint content + blueprint service

**Files:**
- Create: `src/quantuum/domain/mock_blueprint.py`, `src/quantuum/domain/blueprints.py`
- Test: `tests/test_blueprints_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_blueprints_service.py`:
```python
from quantuum.domain.blueprints import create_blueprint, get_blueprint, set_status
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD


async def _profile(session, tenant_id):
    from datetime import date, time
    from decimal import Decimal

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="9")
    profile = NatalProfile(
        tenant_id=tenant_id,
        account_id=acc.id,
        full_name="Test User",
        birth_date=date(1990, 1, 1),
        birth_time=time(12, 0),
        birth_place="Moscow",
        latitude=Decimal("55.75"),
        longitude=Decimal("37.61"),
        timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


def test_mock_blueprint_nonempty():
    assert MOCK_BLUEPRINT_MD.startswith("#")
    assert len(MOCK_BLUEPRINT_MD) > 200


async def test_create_and_transition(session, default_tenant):
    acc, profile = await _profile(session, default_tenant.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
    )
    assert bp.status == "pending"

    await set_status(session, bp.id, "done", llm_md=MOCK_BLUEPRINT_MD)
    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.llm_md == MOCK_BLUEPRINT_MD
    assert reloaded.completed_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_blueprints_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.domain.mock_blueprint'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/domain/mock_blueprint.py`:
```python
MOCK_BLUEPRINT_MD = """# Quantuum SoulMap Blueprint — (mock)

> This is a placeholder report generated without the astrology engine or LLM.
> The real calculator and narrative arrive in a later iteration.

## 🌌 Field Overview

| System | Code / Meaning |
| --- | --- |
| Sun | Capricorn (mock) |
| Moon | Pisces (mock) |
| Rising | Libra (mock) |
| Life Path | 7 (mock) |

## Identity Layer

You are reading a mock Blueprint. Once the engine is ported, this section
will describe your tropical chart, houses, and aspects from your real birth data.

## Timing

The personal-year and transit narrative will appear here in a future version.

---

_Mock content — quantuum-bot foundation MVP._
"""
```

`src/quantuum/domain/blueprints.py`:
```python
from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.db.models import Blueprint

_TERMINAL = {"done", "failed"}


async def create_blueprint(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int
) -> Blueprint:
    blueprint = Blueprint(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        status="pending",
    )
    session.add(blueprint)
    await session.commit()
    await session.refresh(blueprint)
    return blueprint


async def get_blueprint(session, blueprint_id: int) -> Blueprint:
    blueprint = await session.get(Blueprint, blueprint_id)
    if blueprint is None:
        raise NotFoundError("blueprint not found")
    return blueprint


async def set_status(session, blueprint_id: int, status: str, **fields) -> None:
    blueprint = await get_blueprint(session, blueprint_id)
    blueprint.status = status
    for key, value in fields.items():
        setattr(blueprint, key, value)
    if status in _TERMINAL:
        blueprint.completed_at = utcnow()
    session.add(blueprint)
    await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_blueprints_service.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/mock_blueprint.py src/quantuum/domain/blueprints.py tests/test_blueprints_service.py
git commit -m "feat: mock blueprint content and blueprint service"
```

---

## Task 14: Natal profile service

**Files:**
- Create: `src/quantuum/domain/natal_profiles.py`
- Test: add to `tests/test_blueprints_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_blueprints_service.py`:
```python
async def test_natal_profile_upsert(session, default_tenant):
    from datetime import date, time
    from decimal import Decimal

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="42")
    assert await get_natal_profile(session, acc.id) is None

    data = dict(
        full_name="Anna",
        birth_date=date(1980, 6, 24),
        birth_time=time(10, 0),
        birth_place="Moscow",
        latitude=Decimal("55.7558"),
        longitude=Decimal("37.6173"),
        timezone="Europe/Moscow",
    )
    p1 = await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, **data
    )
    data["full_name"] = "Anna B"
    p2 = await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, **data
    )
    assert p1.id == p2.id
    assert p2.full_name == "Anna B"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_blueprints_service.py::test_natal_profile_upsert -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.domain.natal_profiles'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/domain/natal_profiles.py`:
```python
from datetime import date, time
from decimal import Decimal

from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import NatalProfile


async def get_natal_profile(session, account_id: int) -> NatalProfile | None:
    result = await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == account_id)
    )
    return result.scalar_one_or_none()


async def upsert_natal_profile(
    session,
    *,
    tenant_id: int,
    account_id: int,
    full_name: str,
    birth_date: date,
    birth_time: time,
    birth_place: str,
    latitude: Decimal,
    longitude: Decimal,
    timezone: str,
    for_year: int | None = None,
) -> NatalProfile:
    profile = await get_natal_profile(session, account_id)
    if profile is None:
        profile = NatalProfile(tenant_id=tenant_id, account_id=account_id, full_name=full_name,
                               birth_date=birth_date, birth_time=birth_time, birth_place=birth_place,
                               latitude=latitude, longitude=longitude, timezone=timezone,
                               for_year=for_year)
    else:
        profile.full_name = full_name
        profile.birth_date = birth_date
        profile.birth_time = birth_time
        profile.birth_place = birth_place
        profile.latitude = latitude
        profile.longitude = longitude
        profile.timezone = timezone
        profile.for_year = for_year
        profile.updated_at = utcnow()
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_blueprints_service.py::test_natal_profile_upsert -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/natal_profiles.py tests/test_blueprints_service.py
git commit -m "feat: natal profile service"
```

---

## Task 15: Redis client + update queue helpers

**Files:**
- Create: `src/quantuum/redis_client.py`
- Test: `tests/test_redis_queue.py`

- [ ] **Step 1: Write the failing test**

`tests/test_redis_queue.py`:
```python
import pytest_asyncio

from quantuum import redis_client


@pytest_asyncio.fixture
async def redis():
    client = redis_client.get_redis()
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


async def test_push_and_pop_update(redis):
    await redis_client.push_update({"update_id": 1, "text": "hi"})
    item = await redis_client.pop_update(timeout=1)
    assert item == {"update_id": 1, "text": "hi"}


async def test_pop_returns_none_on_timeout(redis):
    item = await redis_client.pop_update(timeout=1)
    assert item is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_redis_queue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.redis_client'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/redis_client.py`:
```python
import json

import redis.asyncio as aioredis

from quantuum.settings import get_settings

_redis: aioredis.Redis | None = None
UPDATE_QUEUE_KEY = "tg:updates"


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def push_update(update: dict) -> None:
    await get_redis().rpush(UPDATE_QUEUE_KEY, json.dumps(update))


async def pop_update(timeout: int = 5) -> dict | None:
    result = await get_redis().blpop([UPDATE_QUEUE_KEY], timeout=timeout)
    if result is None:
        return None
    _, payload = result
    return json.loads(payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_redis_queue.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/redis_client.py tests/test_redis_queue.py
git commit -m "feat: redis client and update queue helpers"
```

---

## Task 16: Logging setup

**Files:**
- Create: `src/quantuum/logging_setup.py`
- Test: `tests/test_logging.py`

- [ ] **Step 1: Write the failing test**

`tests/test_logging.py`:
```python
from quantuum.logging_setup import bind_request_id, configure_logging, get_logger


def test_logging_configures_and_binds():
    configure_logging()
    bind_request_id("abc-123")
    logger = get_logger("test")
    # Should not raise; structlog returns a bound logger.
    logger.info("hello", foo="bar")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.logging_setup'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/logging_setup.py`:
```python
import contextvars
import logging

import structlog

from quantuum.settings import get_settings

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def bind_request_id(request_id: str | None) -> None:
    _request_id.set(request_id)


def _add_request_id(_logger, _method, event_dict):
    rid = _request_id.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging() -> None:
    renderer = (
        structlog.processors.JSONRenderer()
        if get_settings().log_json
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_request_id,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "quantuum"):
    return structlog.get_logger(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_logging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/logging_setup.py tests/test_logging.py
git commit -m "feat: structlog logging with request-id binding"
```

---

## Task 17: API schemas + app factory + health routes

**Files:**
- Create: `src/quantuum/api/__init__.py`, `src/quantuum/api/schemas.py`, `src/quantuum/api/app.py`, `src/quantuum/api/deps.py`, `src/quantuum/api/routes/__init__.py`, `src/quantuum/api/routes/health.py`
- Test: `tests/test_api_health.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_health.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.api.app'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/api/__init__.py` and `src/quantuum/api/routes/__init__.py`:
```python
```

`src/quantuum/api/schemas.py`:
```python
from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class MagicRequestIn(BaseModel):
    email: EmailStr


class MagicRequestOut(BaseModel):
    sent: bool


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str


class RefreshIn(BaseModel):
    refresh_token: str


class MeOut(BaseModel):
    account_id: int
    tenant_id: int


class NatalProfileIn(BaseModel):
    full_name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    for_year: int | None = None


class NatalProfileOut(NatalProfileIn):
    id: int


class BlueprintOut(BaseModel):
    id: int
    status: str
    created_at: str
    completed_at: str | None = None


class BlueprintCreatedOut(BaseModel):
    id: int
    status: str
```

`src/quantuum/api/deps.py`:
```python
from collections.abc import AsyncIterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.auth.jwt_tokens import verify_access_token
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def current_account(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> Account:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verify_access_token(token)
    except Exception as exc:  # jwt errors
        raise HTTPException(status_code=401, detail="invalid token") from exc
    account = await session.get(Account, int(claims["sub"]))
    if account is None or account.status != "active":
        raise HTTPException(status_code=401, detail="account not found")
    return account
```

`src/quantuum/api/routes/health.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import get_session

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {"db": "ok"}
```

`src/quantuum/api/app.py`:
```python
import uuid

from fastapi import FastAPI, Request

from quantuum.api.routes import health
from quantuum.logging_setup import bind_request_id, configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Quantuum API")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        bind_request_id(request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/ tests/test_api_health.py
git commit -m "feat: FastAPI app factory, health routes, current_account dep"
```

---

## Task 18: Magic link service

**Files:**
- Create: `src/quantuum/auth/magic_link.py`
- Test: `tests/test_magic_link.py`

- [ ] **Step 1: Write the failing test**

`tests/test_magic_link.py`:
```python
from quantuum.auth import magic_link


async def test_request_and_consume(monkeypatch, default_tenant):
    sent = {}

    async def fake_send(to_email, link):
        sent["to"] = to_email
        sent["link"] = link

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)

    token = await magic_link.create_magic_token("user@example.com")
    assert "user@example.com" in sent["link"] or token in sent["link"]

    email = await magic_link.consume_magic_token(token)
    assert email == "user@example.com"


async def test_consume_invalid_returns_none():
    assert await magic_link.consume_magic_token("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_magic_link.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.auth.magic_link'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/auth/magic_link.py`:
```python
from quantuum.common.ids import url_safe_token
from quantuum.logging_setup import get_logger
from quantuum.redis_client import get_redis
from quantuum.settings import get_settings

logger = get_logger("magic_link")
_PREFIX = "magic:"


async def create_magic_token(email: str) -> str:
    settings = get_settings()
    token = url_safe_token()
    await get_redis().set(f"{_PREFIX}{token}", email, ex=settings.magic_link_ttl_seconds)
    link = f"{settings.api_host}/auth/magic/consume?token={token}"
    await send_magic_email(email, link)
    return token


async def consume_magic_token(token: str) -> str | None:
    redis = get_redis()
    key = f"{_PREFIX}{token}"
    email = await redis.get(key)
    if email is None:
        return None
    await redis.delete(key)
    return email


async def send_magic_email(to_email: str, link: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("magic_link_email_stub", to=to_email, link=link)
        return
    import aiosmtplib
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = "Your Quantuum sign-in link"
    message.set_content(f"Sign in: {link}")
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_magic_link.py -v`
Expected: PASS (2 tests). Note: requires `redis-test` running (Task 6).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/auth/magic_link.py tests/test_magic_link.py
git commit -m "feat: magic link token service"
```

---

## Task 19: Auth routes

**Files:**
- Create: `src/quantuum/api/routes/auth.py`
- Modify: `src/quantuum/api/app.py` (include router)
- Test: `tests/test_api_auth.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_auth.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import magic_link


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_magic_login_flow(client, monkeypatch):
    async def fake_send(to_email, link):
        return None

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)

    r1 = await client.post("/auth/magic/request", json={"email": "u@example.com"})
    assert r1.status_code == 200
    assert r1.json()["sent"] is True

    token = await magic_link.create_magic_token("u@example.com")
    r2 = await client.get(f"/auth/magic/consume?token={token}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["access_token"]
    assert body["refresh_token"]

    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["tenant_id"] == default_tenant.id


async def test_consume_invalid_token(client):
    r = await client.get("/auth/magic/consume?token=bad")
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_auth.py -v`
Expected: FAIL — `/auth/magic/request` returns 404 (router not mounted).

- [ ] **Step 3: Write the implementation**

`src/quantuum/api/routes/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import get_session
from quantuum.api.schemas import MagicRequestIn, MagicRequestOut, RefreshIn, TokenOut
from quantuum.auth import jwt_tokens, magic_link
from quantuum.auth.identity import find_or_create_account_by_email
from quantuum.common.exceptions import NotFoundError
from quantuum.domain.tenants import get_default_tenant_id

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/magic/request", response_model=MagicRequestOut)
async def magic_request(body: MagicRequestIn) -> MagicRequestOut:
    await magic_link.create_magic_token(body.email)
    return MagicRequestOut(sent=True)


@router.get("/magic/consume", response_model=TokenOut)
async def magic_consume(token: str, session: AsyncSession = Depends(get_session)) -> TokenOut:
    email = await magic_link.consume_magic_token(token)
    if email is None:
        raise HTTPException(status_code=400, detail="invalid or expired token")
    tenant_id = await get_default_tenant_id(session)
    account = await find_or_create_account_by_email(session, tenant_id=tenant_id, email=email)
    access = jwt_tokens.issue_access_token(account.id, tenant_id)
    refresh = await jwt_tokens.issue_refresh_token(session, account.id)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        account = await jwt_tokens.consume_refresh_token(session, body.refresh_token)
    except NotFoundError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    access = jwt_tokens.issue_access_token(account.id, account.tenant_id)
    return TokenOut(access_token=access, refresh_token=body.refresh_token)


@router.post("/logout")
async def logout(body: RefreshIn, session: AsyncSession = Depends(get_session)) -> dict:
    await jwt_tokens.revoke_refresh_token(session, body.refresh_token)
    return {"ok": True}
```

Modify `src/quantuum/api/app.py` — add imports and include routers (the `me` router is added in Task 20; include it now so the auth test's `/v1/me` call works):
```python
from quantuum.api.routes import auth, health, me
```
and inside `create_app`, after `app.include_router(health.router)`:
```python
    app.include_router(auth.router)
    app.include_router(me.router)
```

- [ ] **Step 4: Note**

The `/v1/me` assertion in `test_magic_login_flow` depends on Task 20. Run the invalid-token test in isolation now:

Run: `uv run pytest tests/test_api_auth.py::test_consume_invalid_token -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/routes/auth.py src/quantuum/api/app.py tests/test_api_auth.py
git commit -m "feat: auth routes (magic link, refresh, logout)"
```

---

## Task 20: /v1/me + natal-profile routes

**Files:**
- Create: `src/quantuum/api/routes/me.py`
- Test: `tests/test_api_me.py`, `tests/test_api_natal_profile.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api_me.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_me_requires_auth(client):
    assert (await client.get("/v1/me")).status_code == 401


async def test_me_returns_account(client, session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1")
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id)
    r = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"account_id": acc.id, "tenant_id": default_tenant.id}
```

`tests/test_api_natal_profile.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_me.py tests/test_api_natal_profile.py -v`
Expected: FAIL — routes return 404 / module import error.

- [ ] **Step 3: Write the implementation**

`src/quantuum/api/routes/me.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import current_account, get_session
from quantuum.api.schemas import MeOut, NatalProfileIn, NatalProfileOut
from quantuum.db.models import Account
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
async def get_me(account: Account = Depends(current_account)) -> MeOut:
    return MeOut(account_id=account.id, tenant_id=account.tenant_id)


@router.get("/natal-profile", response_model=NatalProfileOut)
async def read_natal_profile(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> NatalProfileOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="no natal profile")
    return NatalProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone=profile.timezone,
        for_year=profile.for_year,
    )


@router.put("/natal-profile", response_model=NatalProfileOut)
async def write_natal_profile(
    body: NatalProfileIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> NatalProfileOut:
    profile = await upsert_natal_profile(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        full_name=body.full_name,
        birth_date=body.birth_date,
        birth_time=body.birth_time,
        birth_place=body.birth_place,
        latitude=body.latitude,
        longitude=body.longitude,
        timezone=body.timezone,
        for_year=body.for_year,
    )
    return NatalProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone=profile.timezone,
        for_year=profile.for_year,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_me.py tests/test_api_natal_profile.py tests/test_api_auth.py -v`
Expected: PASS (including the previously-deferred `/v1/me` assertion in `test_api_auth.py`).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/routes/me.py tests/test_api_me.py tests/test_api_natal_profile.py
git commit -m "feat: /v1/me and natal-profile routes"
```

---

## Task 21: arq worker + blueprint_generate task (mock)

**Files:**
- Create: `src/quantuum/tasks/__init__.py`, `src/quantuum/tasks/worker.py`, `src/quantuum/tasks/blueprint.py`
- Test: `tests/test_task_blueprint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_task_blueprint.py`:
```python
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.tasks.blueprint import blueprint_generate


async def _setup(session, tenant_id):
    from datetime import date, time
    from decimal import Decimal

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="7")
    profile = await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    bp = await create_blueprint(
        session, tenant_id=tenant_id, account_id=acc.id, natal_profile_id=profile.id
    )
    return acc, bp


async def test_blueprint_generate_sets_done_and_sends(session, default_tenant):
    acc, bp = await _setup(session, default_tenant.id)
    bot = AsyncMock()

    # ctx mimics what arq's startup provides: a sessionmaker and a bot.
    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "bot": bot}
    await blueprint_generate(ctx, bp.id, chat_id=999)

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.llm_md == MOCK_BLUEPRINT_MD
    bot.send_document.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_blueprint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.tasks.blueprint'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/tasks/__init__.py`:
```python
```

`src/quantuum/tasks/blueprint.py`:
```python
from aiogram.types import BufferedInputFile

from quantuum.domain.blueprints import set_status
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD
from quantuum.logging_setup import get_logger

logger = get_logger("task.blueprint")


async def blueprint_generate(ctx, blueprint_id: int, chat_id: int | None = None) -> None:
    sessionmaker = ctx["sessionmaker"]
    bot = ctx["bot"]

    async with sessionmaker() as session:
        await set_status(session, blueprint_id, "calculating", calc_md=MOCK_BLUEPRINT_MD)
        await set_status(
            session,
            blueprint_id,
            "done",
            llm_md=MOCK_BLUEPRINT_MD,
            llm_provider="mock",
            llm_model="mock",
        )

    if chat_id is not None:
        await bot.send_message(chat_id, MOCK_BLUEPRINT_MD[:500])
        await bot.send_document(
            chat_id,
            BufferedInputFile(MOCK_BLUEPRINT_MD.encode(), filename="blueprint.md"),
        )

    logger.info("blueprint_generated", blueprint_id=blueprint_id, chat_id=chat_id)
```

`src/quantuum/tasks/worker.py`:
```python
from aiogram import Bot

from quantuum.db.session import get_sessionmaker
from quantuum.logging_setup import configure_logging
from quantuum.settings import get_settings
from quantuum.tasks.blueprint import blueprint_generate


async def startup(ctx) -> None:
    configure_logging()
    ctx["sessionmaker"] = get_sessionmaker()
    ctx["bot"] = Bot(token=get_settings().bot_token)
    ctx["chat_id_by_account"] = {}


async def shutdown(ctx) -> None:
    bot: Bot = ctx.get("bot")
    if bot is not None:
        await bot.session.close()


class WorkerSettings:
    functions = [blueprint_generate]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

where the import at the top of `worker.py` is:
```python
from arq.connections import RedisSettings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_task_blueprint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/tasks/ tests/test_task_blueprint.py
git commit -m "feat: arq worker and mock blueprint_generate task"
```

---

## Task 22: Blueprint enqueue helper + /v1/me/blueprints routes

**Files:**
- Create: `src/quantuum/tasks/enqueue.py`
- Modify: `src/quantuum/api/routes/me.py`
- Test: `tests/test_api_blueprints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_blueprints.py`:
```python
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

    # No content yet → 409
    dl_empty = await auth_client.get(f"/v1/me/blueprints/{bp_id}/download")
    assert dl_empty.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_blueprints.py -v`
Expected: FAIL — `quantuum.tasks.enqueue` missing / routes 404.

- [ ] **Step 3: Write the enqueue helper**

`src/quantuum/tasks/enqueue.py`:
```python
from arq import create_pool
from arq.connections import RedisSettings

from quantuum.settings import get_settings

_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_blueprint(blueprint_id: int, chat_id: int | None = None) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("blueprint_generate", blueprint_id, chat_id)
```

- [ ] **Step 4: Add blueprint routes to `me.py`**

Append to `src/quantuum/api/routes/me.py` (and extend imports):
```python
from fastapi import Response
from sqlmodel import select

from quantuum.api.schemas import BlueprintCreatedOut, BlueprintOut
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Blueprint
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.tasks import enqueue


@router.post("/blueprints", response_model=BlueprintCreatedOut, status_code=201)
async def create_blueprint_route(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BlueprintCreatedOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=409, detail="natal profile required")
    try:
        charged = await consume_quota(session, account.id, "blueprint")
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail="no quota; buy a plan") from exc

    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id, natal_profile_id=profile.id
    )
    await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    await enqueue.enqueue_blueprint(blueprint.id, None)
    return BlueprintCreatedOut(id=blueprint.id, status=blueprint.status)


@router.get("/blueprints", response_model=list[BlueprintOut])
async def list_blueprints(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[BlueprintOut]:
    result = await session.execute(
        select(Blueprint).where(Blueprint.account_id == account.id).order_by(Blueprint.id.desc())
    )
    return [
        BlueprintOut(
            id=bp.id,
            status=bp.status,
            created_at=bp.created_at.isoformat(),
            completed_at=bp.completed_at.isoformat() if bp.completed_at else None,
        )
        for bp in result.scalars().all()
    ]


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintOut)
async def read_blueprint(
    blueprint_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BlueprintOut:
    bp = await get_blueprint(session, blueprint_id)
    if bp.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    return BlueprintOut(
        id=bp.id,
        status=bp.status,
        created_at=bp.created_at.isoformat(),
        completed_at=bp.completed_at.isoformat() if bp.completed_at else None,
    )


@router.get("/blueprints/{blueprint_id}/download")
async def download_blueprint(
    blueprint_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> Response:
    bp = await get_blueprint(session, blueprint_id)
    if bp.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    if not bp.llm_md:
        raise HTTPException(status_code=409, detail="not ready")
    return Response(
        content=bp.llm_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="blueprint-{bp.id}.md"'},
    )
```

> Note: `get_blueprint` raises `NotFoundError` for a missing id. Add an exception handler so it maps to 404. In `src/quantuum/api/app.py`, inside `create_app` before `return app`:
```python
    from quantuum.common.exceptions import NotFoundError

    @app.exception_handler(NotFoundError)
    async def _not_found(_request, _exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": "not found"})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_blueprints.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/tasks/enqueue.py src/quantuum/api/routes/me.py src/quantuum/api/app.py tests/test_api_blueprints.py
git commit -m "feat: blueprint create/list/get/download routes + enqueue"
```

---

## Task 23: Webhook receiver

**Files:**
- Create: `src/quantuum/api/routes/webhook.py`
- Modify: `src/quantuum/api/app.py` (include router)
- Test: `tests/test_api_webhook.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_webhook.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_webhook.py -v`
Expected: FAIL — route 404 for the valid secret too (router not mounted).

- [ ] **Step 3: Write the implementation**

`src/quantuum/api/routes/webhook.py`:
```python
from fastapi import APIRouter, HTTPException, Request

from quantuum.redis_client import push_update
from quantuum.settings import get_settings

router = APIRouter(tags=["webhook"])


@router.post("/tg/{secret_path}")
async def telegram_webhook(secret_path: str, request: Request) -> dict:
    if secret_path != get_settings().webhook_secret_path:
        raise HTTPException(status_code=404, detail="not found")
    update = await request.json()
    await push_update(update)
    return {"ok": True}
```

Modify `src/quantuum/api/app.py` imports and registration:
```python
from quantuum.api.routes import auth, health, me, webhook
```
and inside `create_app`:
```python
    app.include_router(webhook.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_webhook.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/routes/webhook.py src/quantuum/api/app.py tests/test_api_webhook.py
git commit -m "feat: telegram webhook receiver pushing to redis queue"
```

---

## Task 24: Bot app + account middleware

**Files:**
- Create: `src/quantuum/bot/__init__.py`, `src/quantuum/bot/app.py`, `src/quantuum/bot/middleware/__init__.py`, `src/quantuum/bot/middleware/account.py`
- Test: `tests/test_bot_middleware.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bot_middleware.py`:
```python
from types import SimpleNamespace

from quantuum.bot.middleware.account import AccountMiddleware


async def test_account_middleware_injects_account(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware import account as account_mod

    # Force the middleware to use our test session + tenant.
    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(account_mod, "get_sessionmaker", lambda: _Maker())

    async def fake_default_tenant_id(_s):
        return default_tenant.id

    monkeypatch.setattr(account_mod, "get_default_tenant_id", fake_default_tenant_id)

    captured = {}

    async def handler(event, data):
        captured["account"] = data["account"]
        captured["chat_id"] = data["chat_id"]
        return "ok"

    mw = AccountMiddleware()
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        chat=SimpleNamespace(id=999),
    )
    result = await mw(handler, event, {})
    assert result == "ok"
    assert captured["account"].tenant_id == default_tenant.id
    assert captured["chat_id"] == 999
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.middleware.account'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/bot/__init__.py` and `src/quantuum/bot/middleware/__init__.py`:
```python
```

`src/quantuum/bot/middleware/account.py`:
```python
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.session import get_sessionmaker
from quantuum.domain.accounts import touch_last_seen
from quantuum.domain.tenants import get_default_tenant_id


class AccountMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)
        if from_user is None:
            return await handler(event, data)

        async with get_sessionmaker()() as session:
            tenant_id = await get_default_tenant_id(session)
            account = await find_or_create_account_by_tg(
                session, tenant_id=tenant_id, tg_user_id=str(from_user.id)
            )
            await touch_last_seen(session, account.id)

        data["account"] = account
        data["chat_id"] = chat.id if chat is not None else None
        return await handler(event, data)
```

`src/quantuum/bot/app.py`:
```python
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.bot.middleware.account import AccountMiddleware
from quantuum.settings import get_settings


def create_bot() -> Bot:
    return Bot(token=get_settings().bot_token)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccountMiddleware())
    from quantuum.bot.handlers import blueprint, onboarding, start

    dp.include_router(start.router)
    dp.include_router(onboarding.router)
    dp.include_router(blueprint.router)
    return dp
```

> Note: `create_dispatcher` imports handler routers created in Tasks 25-26. If running this task's test before those exist, temporarily comment the handler imports/includes, or implement Tasks 25-26 first then return. The middleware test does not import `app.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_middleware.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/__init__.py src/quantuum/bot/app.py src/quantuum/bot/middleware/ tests/test_bot_middleware.py
git commit -m "feat: bot app factory and account middleware"
```

---

## Task 25: /start handler + onboarding FSM

**Files:**
- Create: `src/quantuum/bot/handlers/__init__.py`, `src/quantuum/bot/handlers/start.py`, `src/quantuum/bot/handlers/onboarding.py`
- Test: `tests/test_bot_onboarding.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bot_onboarding.py`:
```python
from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.onboarding import parse_coords, parse_birth_date, parse_birth_time


def test_parse_birth_date_valid():
    assert parse_birth_date("1980-06-24") == date(1980, 6, 24)


def test_parse_birth_date_invalid():
    assert parse_birth_date("nonsense") is None


def test_parse_birth_time_valid():
    assert parse_birth_time("10:00") == time(10, 0)


def test_parse_coords_valid():
    assert parse_coords("55.7558, 37.6173") == (Decimal("55.7558"), Decimal("37.6173"))


def test_parse_coords_invalid():
    assert parse_coords("abc") is None


async def test_finish_onboarding_saves_profile(session, default_tenant):
    from quantuum.bot.handlers.onboarding import save_collected_profile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="3")
    profile = await save_collected_profile(
        session,
        account=acc,
        data={
            "full_name": "Anna",
            "birth_date": date(1980, 6, 24),
            "birth_time": time(10, 0),
            "birth_place": "Moscow",
            "latitude": Decimal("55.7558"),
            "longitude": Decimal("37.6173"),
            "timezone": "Europe/Moscow",
        },
    )
    assert profile.id is not None
    assert profile.full_name == "Anna"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_onboarding.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.handlers.onboarding'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/bot/handlers/__init__.py`:
```python
```

`src/quantuum/bot/handlers/onboarding.py`:
```python
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import upsert_natal_profile

router = Router()


class Onboarding(StatesGroup):
    full_name = State()
    birth_date = State()
    birth_time = State()
    birth_place = State()
    coords = State()
    timezone = State()


def parse_birth_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_birth_time(text: str) -> time | None:
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        return None


def parse_coords(text: str) -> tuple[Decimal, Decimal] | None:
    parts = text.replace(" ", "").split(",")
    if len(parts) != 2:
        return None
    try:
        return Decimal(parts[0]), Decimal(parts[1])
    except (InvalidOperation, ValueError):
        return None


async def save_collected_profile(session, *, account: Account, data: dict):
    return await upsert_natal_profile(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        full_name=data["full_name"],
        birth_date=data["birth_date"],
        birth_time=data["birth_time"],
        birth_place=data["birth_place"],
        latitude=data["latitude"],
        longitude=data["longitude"],
        timezone=data["timezone"],
    )


@router.message(Command("profile"))
async def start_onboarding(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.full_name)
    await message.answer("Введи полное имя (как в свидетельстве о рождении):")


@router.message(Onboarding.full_name)
async def on_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text.strip())
    await state.set_state(Onboarding.birth_date)
    await message.answer("Дата рождения в формате ГГГГ-ММ-ДД (например 1980-06-24):")


@router.message(Onboarding.birth_date)
async def on_birth_date(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_date(message.text)
    if parsed is None:
        await message.answer("Не понял дату. Формат ГГГГ-ММ-ДД:")
        return
    await state.update_data(birth_date=parsed.isoformat())
    await state.set_state(Onboarding.birth_time)
    await message.answer("Время рождения ЧЧ:ММ (например 10:00):")


@router.message(Onboarding.birth_time)
async def on_birth_time(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_time(message.text)
    if parsed is None:
        await message.answer("Не понял время. Формат ЧЧ:ММ:")
        return
    await state.update_data(birth_time=parsed.isoformat())
    await state.set_state(Onboarding.birth_place)
    await message.answer("Город рождения (например Moscow):")


@router.message(Onboarding.birth_place)
async def on_birth_place(message: Message, state: FSMContext) -> None:
    await state.update_data(birth_place=message.text.strip())
    await state.set_state(Onboarding.coords)
    await message.answer("Координаты «широта, долгота» (например 55.7558, 37.6173):")


@router.message(Onboarding.coords)
async def on_coords(message: Message, state: FSMContext) -> None:
    parsed = parse_coords(message.text)
    if parsed is None:
        await message.answer("Не понял координаты. Формат «55.7558, 37.6173»:")
        return
    lat, lon = parsed
    await state.update_data(latitude=str(lat), longitude=str(lon))
    await state.set_state(Onboarding.timezone)
    await message.answer("Таймзона IANA (например Europe/Moscow):")


@router.message(Onboarding.timezone)
async def on_timezone(message: Message, state: FSMContext, account: Account) -> None:
    raw = await state.get_data()
    data = {
        "full_name": raw["full_name"],
        "birth_date": parse_birth_date(raw["birth_date"]),
        "birth_time": parse_birth_time(raw["birth_time"]),
        "birth_place": raw["birth_place"],
        "latitude": Decimal(raw["latitude"]),
        "longitude": Decimal(raw["longitude"]),
        "timezone": message.text.strip(),
    }
    async with get_sessionmaker()() as session:
        await save_collected_profile(session, account=account, data=data)
    await state.clear()
    await message.answer("Готово! Профиль сохранён. Команда /blueprint сгенерирует твой разбор.")
```

`src/quantuum/bot/handlers/start.py`:
```python
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile

router = Router()


@router.message(CommandStart())
async def on_start(message: Message, account: Account) -> None:
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
    if profile is None:
        await message.answer(
            "Привет! Я построю твой астрологический разбор. "
            "Заполни профиль командой /profile."
        )
    else:
        await message.answer(
            "С возвращением! Команда /blueprint сгенерирует разбор по твоим данным, "
            "или /profile чтобы их изменить."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_onboarding.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/__init__.py src/quantuum/bot/handlers/start.py src/quantuum/bot/handlers/onboarding.py tests/test_bot_onboarding.py
git commit -m "feat: /start and natal-profile onboarding FSM"
```

---

## Task 26: /blueprint handler

**Files:**
- Create: `src/quantuum/bot/handlers/blueprint.py`
- Test: `tests/test_bot_blueprint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bot_blueprint.py`:
```python
from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.blueprint import request_blueprint_for_account
from quantuum.domain.natal_profiles import upsert_natal_profile


async def test_request_blueprint_no_profile(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1")
    enqueue = AsyncMock()
    status, blueprint_id = await request_blueprint_for_account(
        session, account=acc, chat_id=10, enqueue=enqueue
    )
    assert status == "no_profile"
    enqueue.assert_not_awaited()


async def test_request_blueprint_trial(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="2")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    enqueue = AsyncMock()
    status, blueprint_id = await request_blueprint_for_account(
        session, account=acc, chat_id=10, enqueue=enqueue
    )
    assert status == "queued"
    enqueue.assert_awaited_once_with(blueprint_id, 10)


async def test_request_blueprint_no_quota(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="3")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    enqueue = AsyncMock()
    await request_blueprint_for_account(session, account=acc, chat_id=10, enqueue=enqueue)
    status, _ = await request_blueprint_for_account(
        session, account=acc, chat_id=10, enqueue=enqueue
    )
    assert status == "no_quota"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_blueprint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.handlers.blueprint'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/bot/handlers/blueprint.py`:
```python
from collections.abc import Awaitable, Callable

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.blueprints import create_blueprint
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.tasks.enqueue import enqueue_blueprint

router = Router()


async def request_blueprint_for_account(
    session,
    *,
    account: Account,
    chat_id: int,
    enqueue: Callable[[int, int | None], Awaitable[None]],
) -> tuple[str, int | None]:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "no_profile", None
    try:
        charged = await consume_quota(session, account.id, "blueprint")
    except InsufficientFundsError:
        return "no_quota", None

    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id, natal_profile_id=profile.id
    )
    await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    await enqueue(blueprint.id, chat_id)
    return "queued", blueprint.id


@router.message(Command("blueprint"))
async def on_blueprint(message: Message, account: Account, chat_id: int) -> None:
    async with get_sessionmaker()() as session:
        status, _ = await request_blueprint_for_account(
            session, account=account, chat_id=chat_id, enqueue=enqueue_blueprint
        )
    if status == "no_profile":
        await message.answer("Сначала заполни профиль командой /profile.")
    elif status == "no_quota":
        await message.answer(
            "Бесплатная генерация уже использована. Подписка и пакеты появятся в "
            "следующем обновлении."
        )
    else:
        await message.answer("Генерирую твой разбор, это займёт около минуты…")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_blueprint.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/blueprint.py tests/test_bot_blueprint.py
git commit -m "feat: /blueprint command handler"
```

---

## Task 27: Bot runner (queue consumer)

**Files:**
- Create: `src/quantuum/bot/runner.py`
- Test: `tests/test_bot_runner.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bot_runner.py`:
```python
from unittest.mock import AsyncMock

from quantuum.bot.runner import process_one_update


async def test_process_one_update_feeds_dispatcher():
    dp = AsyncMock()
    bot = AsyncMock()
    update = {"update_id": 1, "message": {"message_id": 1, "text": "hi"}}
    await process_one_update(dp, bot, update)
    dp.feed_raw_update.assert_awaited_once()
    args, kwargs = dp.feed_raw_update.await_args
    assert kwargs.get("bot") is bot or bot in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.runner'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/bot/runner.py`:
```python
import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_bot, create_dispatcher
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update

logger = get_logger("bot.runner")


async def process_one_update(dp: Dispatcher, bot: Bot, update: dict) -> None:
    await dp.feed_raw_update(bot=bot, update=update)


async def run() -> None:
    configure_logging()
    bot = create_bot()
    dp = create_dispatcher()
    logger.info("bot_runner_started")
    while True:
        update = await pop_update(timeout=5)
        if update is None:
            continue
        try:
            await process_one_update(dp, bot, update)
        except Exception:  # keep the loop alive
            logger.exception("update_processing_failed", update_id=update.get("update_id"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/runner.py tests/test_bot_runner.py
git commit -m "feat: bot-worker queue consumer runner"
```

---

## Task 28: Bootstrap on app startup + arq enqueue chat id wiring

**Files:**
- Modify: `src/quantuum/api/app.py` (run bootstrap on startup)
- Modify: `src/quantuum/bot/runner.py` (ensure default tenant exists on startup)
- Test: `tests/test_bootstrap_startup.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bootstrap_startup.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bootstrap_startup.py -v`
Expected: FAIL — no default tenant seeded on startup.

- [ ] **Step 3: Write the implementation**

Modify `src/quantuum/api/app.py` to add a lifespan that seeds the tenant. Replace the `create_app` definition's body opening to include a lifespan:
```python
from contextlib import asynccontextmanager

from quantuum.db.bootstrap import ensure_default_tenant
from quantuum.db.session import get_sessionmaker


@asynccontextmanager
async def _lifespan(app: FastAPI):
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Quantuum API", lifespan=_lifespan)
    ...  # rest unchanged
```

Modify `src/quantuum/bot/runner.py` `run()` to seed before consuming:
```python
async def run() -> None:
    configure_logging()
    from quantuum.db.bootstrap import ensure_default_tenant
    from quantuum.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)

    bot = create_bot()
    dp = create_dispatcher()
    logger.info("bot_runner_started")
    while True:
        update = await pop_update(timeout=5)
        if update is None:
            continue
        try:
            await process_one_update(dp, bot, update)
        except Exception:
            logger.exception("update_processing_failed", update_id=update.get("update_id"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bootstrap_startup.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/api/app.py src/quantuum/bot/runner.py tests/test_bootstrap_startup.py
git commit -m "feat: seed default tenant on api and bot-worker startup"
```

---

## Task 29: Lint pass + full suite + manual smoke

**Files:** none (verification task)

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check src tests`
Expected: no errors (fix any reported issues, then re-run).

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 3: Build and start the full stack**

Run: `cp .env.example .env` then set a real `BOT_TOKEN` and a random `WEBHOOK_SECRET_PATH` in `.env`, then:
```bash
docker compose up --build -d
docker compose ps
```
Expected: `postgres`, `redis`, `api`, `bot-worker`, `task-worker` up; `migration` exited 0.

- [ ] **Step 4: Smoke-test the API**

Run: `curl -s localhost:8000/healthz && echo && curl -s localhost:8000/readyz`
Expected: `{"status":"ok"}` then `{"db":"ok"}`.

- [ ] **Step 5: Register the webhook and smoke-test the bot**

Run (substitute token + secret + public URL):
```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<PUBLIC_API_HOST>/tg/<WEBHOOK_SECRET_PATH>"
```
Then in Telegram: `/start` → `/profile` → walk the steps → `/blueprint`.
Expected: bot replies "Генерирую…", then within ~seconds delivers the mock preview message + `blueprint.md` document.

- [ ] **Step 6: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint pass and smoke verification"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage (Plan 1 slice):** project skeleton ✓, docker-compose 3 processes ✓, Postgres+Redis ✓, Alembic ✓, models for the MVP subset ✓, magic-link auth + JWT ✓, webhook→queue→bot-worker ✓, arq task-worker ✓, mock blueprint pipeline with trial quota ✓, `.md` delivery ✓. Multi-tenancy logic, payments, real astrology, admin API, i18n are intentionally deferred to Plans 2-5 (see spec §"Non-goals" and this plan's Context).
- **Single-tenant seam:** every domain row already stores `tenant_id` via `get_default_tenant_id`; Plan 2 swaps that helper for real resolution without schema churn.
- **Type consistency:** task signatures (`consume_quota`, `create_blueprint`, `set_status`, `find_or_create_account_by_*`, `enqueue_blueprint(blueprint_id, chat_id)`, `request_blueprint_for_account`) are used identically across API routes, bot handlers, and the arq task.

---

## Execution Handoff

(Filled in after user picks an execution approach.)
