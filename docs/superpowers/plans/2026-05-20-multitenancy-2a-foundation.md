# Multi-tenancy 2a — Tenancy Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move from a single hardcoded "default" tenant to real per-bot tenant resolution: bots and roles live in the DB (tokens encrypted), every Telegram update resolves its tenant from the originating bot, and the runtime can run a pool of bots — while the existing single bot keeps working unchanged.

**Architecture:** Add `tenant_bots` and `tenant_roles` tables and extend `Tenant`. A `TenantMiddleware` resolves `tenant_id` from `data["bot"].id` (aiogram derives the bot id from its token, no API call) before `AccountMiddleware`. The webhook receiver resolves the tenant bot by `webhook_secret_path` from the DB and enqueues `{bot_id, update}`; the bot-worker dispatches via a Bot pool. Bootstrap migrates the env `BOT_TOKEN` into an encrypted `tenant_bots` row.

**Tech Stack:** Python 3.12, aiogram 3.x, SQLModel + Alembic, `cryptography` (Fernet) for token encryption, Redis, pytest. Builds on `main` (Plan 1 + bot UX).

---

## Context

Spec: `docs/superpowers/specs/2026-05-19-quantuum-bot-platform-design.md` (§4 data model, §5 auth, §8 — onboarding is Plan 2b, not here).

Current state (in `main`):
- `src/quantuum/db/models.py` — `Tenant(id, slug, display_name, status, created_at)` minimal; `_dt_field()` helper for timestamptz columns; `Account`, `AccountIdentity`, etc.
- `src/quantuum/domain/tenants.py` — `get_default_tenant_id(session)` (looks up `slug == settings.default_tenant_slug`).
- `src/quantuum/db/bootstrap.py` — `ensure_default_tenant(session)`.
- `src/quantuum/bot/middleware/account.py` — `AccountMiddleware` resolves tenant via `get_default_tenant_id`, then account by `from_user.id`.
- `src/quantuum/bot/app.py` — `create_dispatcher()` (RedisStorage; `AccountMiddleware` on message + callback_query; routers `start, generate, profile, history, onboarding, menu`).
- `src/quantuum/bot/polling.py` — single `create_bot()` (token from `settings.bot_token`), `dp.start_polling(bot)`.
- `src/quantuum/bot/runner.py` — webhook consumer: `pop_update()` → `dp.feed_raw_update(bot=create_bot(), update=update)`.
- `src/quantuum/api/routes/webhook.py` — `POST /tg/{secret_path}`; checks `secret_path == settings.webhook_secret_path`; `push_update(update)`.
- `src/quantuum/redis_client.py` — `push_update(update: dict)`, `pop_update(timeout) -> dict | None`, key `tg:updates`.
- `src/quantuum/settings.py` — `bot_token`, `webhook_secret_path`, `redis_url`, `default_tenant_slug`, etc.
- Tests run via `uv run pytest` (conftest sets env to static-IP test DB/redis). Full suite currently 82 green.

**Scope (2a):** data model + resolution + crypto + bot pool runtime. **Out (2b):** master bot, `tenant_invites`, superadmin API, provisioning. **Out (later plans):** payments, i18n, admin API, real astrology.

**Key fact used throughout:** aiogram `Bot.id` is parsed from the token (`int(token.split(":")[0])`) with no network call; `tenant_bots.bot_telegram_id` is set the same way at bootstrap, so `bot.id` ↔ `tenant_bots` resolution is exact and offline-safe.

## File structure

```
src/quantuum/
  settings.py                 # + bot_token_enc_key, default_bot_transport
  common/crypto.py            # encrypt_token / decrypt_token (Fernet)
  db/models.py                # extend Tenant; + TenantBot, TenantRole
  db/bootstrap.py             # + ensure_default_tenant_bot
  domain/tenants.py           # + resolve_tenant_id_by_bot, get_tenant_bot_by_webhook_secret,
                              #   list_active_tenant_bots, grant_role, account_has_role
  bot/middleware/tenant.py    # TenantMiddleware (bot.id -> tenant_id)
  bot/middleware/account.py   # use data["tenant_id"]
  bot/botpool.py              # build_bots(tenant_bots) -> {bot_id: Bot}
  bot/app.py                  # register TenantMiddleware before AccountMiddleware
  bot/polling.py              # poll all active polling bots from DB
  bot/runner.py               # webhook consumer dispatches via Bot pool
  redis_client.py             # queue carries bot_id envelope
  api/routes/webhook.py       # resolve tenant bot by webhook_secret_path from DB
  alembic/versions/<new>.py   # migration
tests/
  conftest.py                 # + BOT_TOKEN_ENC_KEY env
```

## Locked signatures

```python
# common/crypto.py
def encrypt_token(token: str) -> bytes: ...
def decrypt_token(blob: bytes) -> str: ...

# db/models.py
class TenantBot(SQLModel, table=True):   # __tablename__ = "tenant_bots"
    id, tenant_id(FK,index), bot_telegram_id(int|None, unique index), bot_username(str|None),
    bot_token_enc(bytes), transport(str="polling"), webhook_secret_path(str, unique index),
    status(str="active"), created_at, updated_at
class TenantRole(SQLModel, table=True):  # __tablename__ = "tenant_roles"
    id, tenant_id(FK,index), account_id(FK,index), role(str),
    granted_by_account_id(int|None), granted_at
    # UniqueConstraint(tenant_id, account_id, role)
# Tenant gains: tier(str="basic"), is_platform(bool=False),
#   primary_owner_account_id(int|None), owner_tg_id(str|None), owner_chat_id(str|None)

# domain/tenants.py
async def resolve_tenant_id_by_bot(session, bot_telegram_id: int) -> int | None: ...
async def get_tenant_bot_by_webhook_secret(session, secret: str) -> TenantBot | None: ...
async def list_active_tenant_bots(session, transport: str | None = None) -> list[TenantBot]: ...
async def grant_role(session, *, tenant_id: int, account_id: int, role: str, granted_by_account_id: int | None = None) -> None: ...
async def account_has_role(session, *, tenant_id: int, account_id: int, role: str) -> bool: ...

# db/bootstrap.py
async def ensure_default_tenant_bot(session) -> None: ...   # idempotent; needs default tenant + settings.bot_token

# bot/botpool.py
def build_bots(tenant_bots: list) -> dict[int, "aiogram.Bot"]: ...   # keyed by bot_telegram_id

# redis_client.py
async def push_update(bot_id: int, update: dict) -> None: ...
async def pop_update(timeout: int = 5) -> dict | None: ...   # returns {"bot_id": int, "update": dict} | None
```

---

## Task 1: Token encryption (crypto) + settings + conftest key

**Files:**
- Modify: `src/quantuum/settings.py`, `.env.example`, `tests/conftest.py`
- Create: `src/quantuum/common/crypto.py`
- Test: `tests/test_crypto.py`
- Modify: `pyproject.toml` (add `cryptography`)

- [ ] **Step 1: Add the dependency**

Run: `uv add cryptography`
Expected: `cryptography` added to `pyproject.toml` + `uv.lock` updated.

- [ ] **Step 2: Write the failing test**

`tests/test_crypto.py`:
```python
from quantuum.common.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip():
    token = "811895373:AAEHJCCl-secret"
    blob = encrypt_token(token)
    assert isinstance(blob, bytes)
    assert blob != token.encode()
    assert decrypt_token(blob) == token
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.common.crypto'`

- [ ] **Step 4: Add settings field + implement crypto**

In `src/quantuum/settings.py`, add fields to `Settings` (after `webhook_secret_path`):
```python
    bot_token_enc_key: str = ""
    default_bot_transport: str = "polling"
```

`src/quantuum/common/crypto.py`:
```python
from cryptography.fernet import Fernet

from quantuum.settings import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().bot_token_enc_key.encode())


def encrypt_token(token: str) -> bytes:
    return _fernet().encrypt(token.encode())


def decrypt_token(blob: bytes) -> str:
    return _fernet().decrypt(blob).decode()
```

- [ ] **Step 5: Provide a key for tests and dev**

Generate ONE real Fernet key (do NOT invent a literal — an invalid key makes `Fernet()` raise at construction):
```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Take the printed value (call it `$KEY`, a 44-char base64 string ending in `=`). Use that exact value in both places:

In `tests/conftest.py`, add to the `os.environ.setdefault(...)` block near the top:
```python
os.environ.setdefault("BOT_TOKEN_ENC_KEY", "$KEY")  # paste the generated key here
```
In `.env.example`, add:
```bash
BOT_TOKEN_ENC_KEY=$KEY
DEFAULT_BOT_TRANSPORT=polling
```
(For production, generate a fresh key the same way and keep it secret.)

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_crypto.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/quantuum/common/crypto.py src/quantuum/settings.py .env.example tests/conftest.py tests/test_crypto.py
git commit -m "feat: bot-token encryption (Fernet) + settings"
```

---

## Task 2: Extend Tenant + TenantBot + TenantRole models

**Files:**
- Modify: `src/quantuum/db/models.py`
- Test: `tests/test_db_models.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db_models.py`:
```python
def test_tenant_bot_and_role_tables_registered():
    names = set(models.SQLModel.metadata.tables.keys())
    assert {"tenant_bots", "tenant_roles"} <= names


def test_tenant_has_tenancy_fields():
    t = models.Tenant(slug="x", display_name="X")
    assert t.tier == "basic"
    assert t.is_platform is False
    assert t.primary_owner_account_id is None


def test_tenant_bot_defaults():
    tb = models.TenantBot(tenant_id=1, bot_token_enc=b"x", webhook_secret_path="s")
    assert tb.transport == "polling"
    assert tb.status == "active"
    assert tb.bot_telegram_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_models.py::test_tenant_bot_and_role_tables_registered -v`
Expected: FAIL with `AttributeError: module 'quantuum.db.models' has no attribute 'TenantBot'`

- [ ] **Step 3: Write the implementation**

In `src/quantuum/db/models.py`:
- Add `from sqlalchemy import UniqueConstraint` to the imports (alongside the existing `from sqlalchemy import DateTime`).
- Extend the `Tenant` class body (keep existing fields, add these before `created_at`):
```python
    tier: str = "basic"  # basic|vip
    is_platform: bool = False
    primary_owner_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    owner_tg_id: str | None = None
    owner_chat_id: str | None = None
```
- Add two new model classes (place after the `Tenant` class):
```python
class TenantBot(SQLModel, table=True):
    __tablename__ = "tenant_bots"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    bot_telegram_id: int | None = Field(default=None, unique=True, index=True)
    bot_username: str | None = None
    bot_token_enc: bytes
    transport: str = "polling"  # polling|webhook
    webhook_secret_path: str = Field(unique=True, index=True)
    status: str = "active"  # active|paused|error
    created_at: datetime = _dt_field(default_factory=utcnow)
    updated_at: datetime = _dt_field(default_factory=utcnow)


class TenantRole(SQLModel, table=True):
    __tablename__ = "tenant_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "role"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    role: str  # owner|admin|...
    granted_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    granted_at: datetime = _dt_field(default_factory=utcnow)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_models.py -q`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/db/models.py tests/test_db_models.py
git commit -m "feat: TenantBot, TenantRole models + Tenant tenancy fields"
```

---

## Task 3: Alembic migration

**Files:**
- Generated: `alembic/versions/<rev>_tenancy.py`

- [ ] **Step 1: Generate the migration**

Run (test DB env is set in conftest, but alembic needs it explicitly):
```bash
DATABASE_URL=postgresql+asyncpg://quantuum:quantuum@172.30.0.2:5432/quantuum_test \
REDIS_URL=redis://172.30.0.3:6379/0 JWT_SIGNING_KEY=test \
uv run alembic revision --autogenerate -m "tenancy: tenant_bots, tenant_roles, tenant fields"
```
Expected: a new version file. OPEN it and confirm it: `create_table("tenant_bots")`, `create_table("tenant_roles")`, and `add_column` for `tenants.tier/is_platform/primary_owner_account_id/owner_tg_id/owner_chat_id`. Confirm `import sqlmodel` is present (the template adds it).

- [ ] **Step 2: Apply and verify**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://quantuum:quantuum@172.30.0.2:5432/quantuum_test \
REDIS_URL=redis://172.30.0.3:6379/0 JWT_SIGNING_KEY=test \
uv run alembic upgrade head
```
Expected: `Running upgrade ... tenancy`, exits 0.

- [ ] **Step 3: Verify no drift**

Re-run the autogenerate command from Step 1 with message `drift-check`; open the generated file; its `upgrade()` body must be just `pass`. Then delete that drift-check file (`rm alembic/versions/*drift_check*.py`). Keep only the real tenancy migration.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: alembic migration for tenancy tables/fields"
```

---

## Task 4: Tenant resolution + role helpers

**Files:**
- Modify: `src/quantuum/domain/tenants.py`
- Test: `tests/test_tenant_resolution.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tenant_resolution.py`:
```python
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import TenantBot
from quantuum.domain.tenants import (
    account_has_role,
    grant_role,
    get_tenant_bot_by_webhook_secret,
    list_active_tenant_bots,
    resolve_tenant_id_by_bot,
)


async def _bot(session, tenant_id, *, bot_id, secret, transport="polling", status="active"):
    tb = TenantBot(
        tenant_id=tenant_id, bot_telegram_id=bot_id, bot_token_enc=b"enc",
        webhook_secret_path=secret, transport=transport, status=status,
    )
    session.add(tb)
    await session.commit()
    await session.refresh(tb)
    return tb


async def test_resolve_tenant_id_by_bot(session, default_tenant):
    await _bot(session, default_tenant.id, bot_id=111, secret="s1")
    assert await resolve_tenant_id_by_bot(session, 111) == default_tenant.id
    assert await resolve_tenant_id_by_bot(session, 999) is None


async def test_get_tenant_bot_by_webhook_secret(session, default_tenant):
    await _bot(session, default_tenant.id, bot_id=222, secret="abc")
    tb = await get_tenant_bot_by_webhook_secret(session, "abc")
    assert tb is not None and tb.bot_telegram_id == 222
    assert await get_tenant_bot_by_webhook_secret(session, "nope") is None


async def test_list_active_tenant_bots_filters(session, default_tenant):
    await _bot(session, default_tenant.id, bot_id=1, secret="a", transport="polling")
    await _bot(session, default_tenant.id, bot_id=2, secret="b", transport="webhook")
    await _bot(session, default_tenant.id, bot_id=3, secret="c", transport="polling", status="paused")
    polling = await list_active_tenant_bots(session, transport="polling")
    assert {tb.bot_telegram_id for tb in polling} == {1}  # active + polling only
    all_active = await list_active_tenant_bots(session)
    assert {tb.bot_telegram_id for tb in all_active} == {1, 2}


async def test_roles(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="5")
    assert await account_has_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner") is False
    await grant_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner")
    assert await account_has_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner") is True
    # idempotent (unique constraint not violated on re-grant)
    await grant_role(session, tenant_id=default_tenant.id, account_id=acc.id, role="owner")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tenant_resolution.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_tenant_id_by_bot'`

- [ ] **Step 3: Write the implementation**

Append to `src/quantuum/domain/tenants.py` (keep the existing `get_default_tenant_id`):
```python
from quantuum.db.models import TenantBot, TenantRole


async def resolve_tenant_id_by_bot(session, bot_telegram_id: int) -> int | None:
    result = await session.execute(
        select(TenantBot.tenant_id).where(
            TenantBot.bot_telegram_id == bot_telegram_id, TenantBot.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_bot_by_webhook_secret(session, secret: str) -> TenantBot | None:
    result = await session.execute(
        select(TenantBot).where(
            TenantBot.webhook_secret_path == secret, TenantBot.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def list_active_tenant_bots(session, transport: str | None = None) -> list[TenantBot]:
    query = select(TenantBot).where(TenantBot.status == "active")
    if transport is not None:
        query = query.where(TenantBot.transport == transport)
    result = await session.execute(query)
    return list(result.scalars().all())


async def grant_role(
    session, *, tenant_id: int, account_id: int, role: str, granted_by_account_id: int | None = None
) -> None:
    if await account_has_role(session, tenant_id=tenant_id, account_id=account_id, role=role):
        return
    session.add(
        TenantRole(
            tenant_id=tenant_id, account_id=account_id, role=role,
            granted_by_account_id=granted_by_account_id,
        )
    )
    await session.commit()


async def account_has_role(session, *, tenant_id: int, account_id: int, role: str) -> bool:
    result = await session.execute(
        select(TenantRole.id).where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.account_id == account_id,
            TenantRole.role == role,
        )
    )
    return result.scalar_one_or_none() is not None
```
(`select` is already imported at the top of the module.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tenant_resolution.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/tenants.py tests/test_tenant_resolution.py
git commit -m "feat: tenant resolution by bot + role helpers"
```

---

## Task 5: Bootstrap — migrate env BOT_TOKEN into a DB bot row

**Files:**
- Modify: `src/quantuum/db/bootstrap.py`
- Test: `tests/test_bootstrap_bot.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bootstrap_bot.py`:
```python
import os

from sqlmodel import select

from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
from quantuum.db.models import TenantBot
from quantuum.common.crypto import decrypt_token


async def test_ensure_default_tenant_bot_idempotent(session, monkeypatch):
    # conftest sets BOT_TOKEN="123:test"; bot id is the token prefix.
    monkeypatch.setenv("BOT_TOKEN", "777:secrettoken")
    from quantuum.settings import get_settings
    get_settings.cache_clear()

    tenant = await ensure_default_tenant(session)
    await ensure_default_tenant_bot(session)
    await ensure_default_tenant_bot(session)  # idempotent

    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant.id))
    bots = result.scalars().all()
    assert len(bots) == 1
    tb = bots[0]
    assert tb.bot_telegram_id == 777
    assert decrypt_token(tb.bot_token_enc) == "777:secrettoken"
    get_settings.cache_clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bootstrap_bot.py -v`
Expected: FAIL with `ImportError: cannot import name 'ensure_default_tenant_bot'`

- [ ] **Step 3: Write the implementation**

Append to `src/quantuum/db/bootstrap.py`:
```python
from sqlmodel import select  # already imported at top; keep single import

from quantuum.common.crypto import encrypt_token
from quantuum.db.models import TenantBot
from quantuum.domain.tenants import get_default_tenant_id


async def ensure_default_tenant_bot(session) -> None:
    """Migrate the env BOT_TOKEN into a tenant_bots row for the default tenant (idempotent)."""
    settings = get_settings()
    token = settings.bot_token
    if not token:
        return
    bot_id = int(token.split(":")[0])
    existing = await session.execute(
        select(TenantBot).where(TenantBot.bot_telegram_id == bot_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    tenant_id = await get_default_tenant_id(session)
    session.add(
        TenantBot(
            tenant_id=tenant_id,
            bot_telegram_id=bot_id,
            bot_token_enc=encrypt_token(token),
            transport=settings.default_bot_transport,
            webhook_secret_path=settings.webhook_secret_path or f"tg-{bot_id}",
        )
    )
    await session.commit()
```
(Ensure `from quantuum.settings import get_settings` is already imported at the top of bootstrap.py — it is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bootstrap_bot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/db/bootstrap.py tests/test_bootstrap_bot.py
git commit -m "feat: bootstrap default tenant bot from env token"
```

---

## Task 6: TenantMiddleware + AccountMiddleware uses resolved tenant

**Files:**
- Create: `src/quantuum/bot/middleware/tenant.py`
- Modify: `src/quantuum/bot/middleware/account.py`
- Test: `tests/test_tenant_middleware.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tenant_middleware.py`:
```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.bot.middleware.tenant import TenantMiddleware
from quantuum.db.models import TenantBot


async def test_tenant_middleware_resolves_from_bot(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware import tenant as tenant_mod

    session.add(TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=555, bot_token_enc=b"e",
        webhook_secret_path="w555",
    ))
    await session.commit()

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(tenant_mod, "get_sessionmaker", lambda: _Maker())

    captured = {}

    async def handler(event, data):
        captured["tenant_id"] = data.get("tenant_id")
        return "ok"

    mw = TenantMiddleware()
    bot = SimpleNamespace(id=555)
    assert await mw(handler, SimpleNamespace(from_user=SimpleNamespace(id=1)), {"bot": bot}) == "ok"
    assert captured["tenant_id"] == default_tenant.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tenant_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.middleware.tenant'`

- [ ] **Step 3: Write `tenant.py`**

`src/quantuum/bot/middleware/tenant.py`:
```python
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import resolve_tenant_id_by_bot


class TenantMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        if bot is not None:
            async with get_sessionmaker()() as session:
                data["tenant_id"] = await resolve_tenant_id_by_bot(session, bot.id)
        return await handler(event, data)
```

- [ ] **Step 4: Update `account.py` to use the resolved tenant**

Replace `src/quantuum/bot/middleware/account.py` with:
```python
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.session import get_sessionmaker
from quantuum.domain.accounts import touch_last_seen


class AccountMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)
        tenant_id = data.get("tenant_id")
        if from_user is None or tenant_id is None:
            return await handler(event, data)

        async with get_sessionmaker()() as session:
            account = await find_or_create_account_by_tg(
                session, tenant_id=tenant_id, tg_user_id=str(from_user.id)
            )
            await touch_last_seen(session, account.id)

        data["account"] = account
        data["chat_id"] = chat.id if chat is not None else None
        return await handler(event, data)
```
NOTE: `AccountMiddleware` no longer imports `get_default_tenant_id`. It now requires `data["tenant_id"]` to be set by `TenantMiddleware` (registered before it). If `tenant_id` is None (unknown bot), it passes through without injecting an account — handlers requiring `account` simply won't fire for unknown bots.

- [ ] **Step 5: Update the existing middleware test**

`tests/test_bot_middleware.py` (from Plan 1) monkeypatches `get_sessionmaker` and `get_default_tenant_id` on the account module and passes an event without `tenant_id`. Update it so the account middleware receives `tenant_id` in `data`: change the call
```python
    result = await mw(handler, event, {})
```
to
```python
    result = await mw(handler, event, {"tenant_id": default_tenant.id})
```
and remove the now-irrelevant `monkeypatch.setattr(account_mod, "get_default_tenant_id", ...)` line (the account middleware no longer calls it). Keep the `get_sessionmaker` monkeypatch.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenant_middleware.py tests/test_bot_middleware.py -q` then `uv run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: TenantMiddleware resolves tenant by bot; account middleware uses it"
```

---

## Task 7: Bot pool builder

**Files:**
- Create: `src/quantuum/bot/botpool.py`
- Test: `tests/test_botpool.py`

- [ ] **Step 1: Write the failing test**

`tests/test_botpool.py`:
```python
from quantuum.bot.botpool import build_bots
from quantuum.common.crypto import encrypt_token
from quantuum.db.models import TenantBot


def test_build_bots_keyed_by_bot_id():
    rows = [
        TenantBot(tenant_id=1, bot_telegram_id=111, bot_token_enc=encrypt_token("111:aaa"),
                  webhook_secret_path="a"),
        TenantBot(tenant_id=2, bot_telegram_id=222, bot_token_enc=encrypt_token("222:bbb"),
                  webhook_secret_path="b"),
    ]
    bots = build_bots(rows)
    assert set(bots.keys()) == {111, 222}
    assert bots[111].id == 111
    assert bots[222].id == 222


def test_build_bots_skips_rows_without_telegram_id():
    rows = [TenantBot(tenant_id=1, bot_telegram_id=None, bot_token_enc=encrypt_token("9:x"),
                      webhook_secret_path="z")]
    assert build_bots(rows) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_botpool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.botpool'`

- [ ] **Step 3: Write the implementation**

`src/quantuum/bot/botpool.py`:
```python
from aiogram import Bot

from quantuum.common.crypto import decrypt_token


def build_bots(tenant_bots: list) -> dict[int, Bot]:
    """Build aiogram Bot instances keyed by bot_telegram_id (rows without an id are skipped)."""
    pool: dict[int, Bot] = {}
    for tb in tenant_bots:
        if tb.bot_telegram_id is None:
            continue
        pool[tb.bot_telegram_id] = Bot(token=decrypt_token(tb.bot_token_enc))
    return pool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_botpool.py -v`
Expected: PASS (2 tests). (`Bot(token=...)` does not hit the network; `Bot.id` is parsed from the token.)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/botpool.py tests/test_botpool.py
git commit -m "feat: bot pool builder from tenant_bots"
```

---

## Task 8: Update Redis queue to carry bot_id

**Files:**
- Modify: `src/quantuum/redis_client.py`
- Test: `tests/test_redis_queue.py` (update)

- [ ] **Step 1: Update the test**

Replace the two test bodies in `tests/test_redis_queue.py`:
```python
async def test_push_and_pop_update(redis):
    await redis_client.push_update(555, {"update_id": 1, "text": "hi"})
    item = await redis_client.pop_update(timeout=1)
    assert item == {"bot_id": 555, "update": {"update_id": 1, "text": "hi"}}


async def test_pop_returns_none_on_timeout(redis):
    item = await redis_client.pop_update(timeout=1)
    assert item is None
```
(Keep the `redis` fixture unchanged.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_redis_queue.py -v`
Expected: FAIL — `push_update` now takes 2 args / envelope shape differs.

- [ ] **Step 3: Update the implementation**

In `src/quantuum/redis_client.py`, change `push_update`/`pop_update`:
```python
async def push_update(bot_id: int, update: dict) -> None:
    await get_redis().rpush(UPDATE_QUEUE_KEY, json.dumps({"bot_id": bot_id, "update": update}))


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
git commit -m "refactor: queue envelope carries bot_id"
```

---

## Task 9: Webhook receiver resolves tenant bot from DB

**Files:**
- Modify: `src/quantuum/api/routes/webhook.py`
- Test: `tests/test_api_webhook.py` (update)

- [ ] **Step 1: Update the test**

Replace `tests/test_api_webhook.py` with:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum import redis_client
from quantuum.api.app import create_app
from quantuum.db.models import TenantBot


@pytest_asyncio.fixture
async def client(engine, session, default_tenant):
    await redis_client.get_redis().flushdb()
    session.add(TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=4242, bot_token_enc=b"e",
        webhook_secret_path="hook-4242", transport="webhook",
    ))
    await session.commit()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await redis_client.get_redis().flushdb()


async def test_webhook_unknown_secret_404(client):
    r = await client.post("/tg/nope", json={"update_id": 1})
    assert r.status_code == 404


async def test_webhook_pushes_update_with_bot_id(client):
    r = await client.post("/tg/hook-4242", json={"update_id": 9, "message": {"text": "hi"}})
    assert r.status_code == 200
    item = await redis_client.pop_update(timeout=2)
    assert item["bot_id"] == 4242
    assert item["update"]["update_id"] == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_webhook.py -v`
Expected: FAIL — current webhook checks `settings.webhook_secret_path` and pushes without bot_id.

- [ ] **Step 3: Update the implementation**

Replace `src/quantuum/api/routes/webhook.py` with:
```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import get_session
from quantuum.domain.tenants import get_tenant_bot_by_webhook_secret
from quantuum.redis_client import push_update

router = APIRouter(tags=["webhook"])


@router.post("/tg/{secret_path}")
async def telegram_webhook(
    secret_path: str, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    tenant_bot = await get_tenant_bot_by_webhook_secret(session, secret_path)
    if tenant_bot is None or tenant_bot.bot_telegram_id is None:
        raise HTTPException(status_code=404, detail="not found")
    update = await request.json()
    await push_update(tenant_bot.bot_telegram_id, update)
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_webhook.py -v` then `uv run pytest -q`
Expected: PASS (2 webhook tests); full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/routes/webhook.py tests/test_api_webhook.py
git commit -m "feat: webhook resolves tenant bot from DB, enqueues bot_id"
```

---

## Task 10: Bot-worker runtime — pool-based polling + webhook consumer

**Files:**
- Modify: `src/quantuum/bot/polling.py`, `src/quantuum/bot/runner.py`
- Test: `tests/test_bot_runner.py` (update)

- [ ] **Step 1: Update the runner test**

Replace `tests/test_bot_runner.py` with:
```python
from unittest.mock import AsyncMock

from quantuum.bot.runner import process_one_envelope


async def test_process_one_envelope_dispatches_with_pooled_bot():
    dp = AsyncMock()
    bot = AsyncMock()
    pool = {42: bot}
    await process_one_envelope(dp, pool, {"bot_id": 42, "update": {"update_id": 1}})
    dp.feed_raw_update.assert_awaited_once()
    _, kwargs = dp.feed_raw_update.await_args
    assert kwargs["bot"] is bot


async def test_process_one_envelope_skips_unknown_bot():
    dp = AsyncMock()
    await process_one_envelope(dp, {}, {"bot_id": 99, "update": {"update_id": 1}})
    dp.feed_raw_update.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_runner.py -v`
Expected: FAIL — `process_one_envelope` does not exist (current runner has `process_one_update`).

- [ ] **Step 3: Rewrite `runner.py` (webhook consumer over a Bot pool)**

`src/quantuum/bot/runner.py`:
```python
import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update

logger = get_logger("bot.runner")


async def process_one_envelope(dp: Dispatcher, pool: dict[int, Bot], envelope: dict) -> None:
    bot = pool.get(envelope["bot_id"])
    if bot is None:
        logger.warning("update_for_unknown_bot", bot_id=envelope["bot_id"])
        return
    await dp.feed_raw_update(bot=bot, update=envelope["update"])


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        rows = await list_active_tenant_bots(session, transport="webhook")
    pool = build_bots(rows)
    dp = create_dispatcher()
    logger.info("bot_runner_started", webhook_bots=len(pool))
    while True:
        envelope = await pop_update(timeout=5)
        if envelope is None:
            continue
        try:
            await process_one_envelope(dp, pool, envelope)
        except Exception:
            logger.exception("update_processing_failed", bot_id=envelope.get("bot_id"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rewrite `polling.py` (poll all active polling bots)**

`src/quantuum/bot/polling.py`:
```python
"""Local/dev long-polling entrypoint: polls every active polling-transport bot."""

import asyncio

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger

logger = get_logger("bot.polling")


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        rows = await list_active_tenant_bots(session, transport="polling")
    pool = build_bots(rows)
    dp = create_dispatcher()
    for bot in pool.values():
        await bot.delete_webhook(drop_pending_updates=True)
    logger.info("bot_polling_started", polling_bots=len(pool))
    if not pool:
        logger.warning("no_polling_bots_configured")
        return
    await dp.start_polling(*pool.values())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot_runner.py -q` then `uv run pytest -q`
Expected: PASS (2 runner tests); full suite green.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/runner.py src/quantuum/bot/polling.py tests/test_bot_runner.py
git commit -m "feat: bot-worker runs a Bot pool (multi-bot polling + webhook consumer)"
```

---

## Task 11: Register TenantMiddleware in the dispatcher

**Files:**
- Modify: `src/quantuum/bot/app.py`
- Test: `tests/test_menu_and_dispatcher.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_menu_and_dispatcher.py`:
```python
def test_tenant_middleware_registered_before_account():
    from quantuum.bot.app import create_dispatcher
    from quantuum.bot.middleware.account import AccountMiddleware
    from quantuum.bot.middleware.tenant import TenantMiddleware

    dp = create_dispatcher()
    msg_mw = list(dp.message.middleware)
    types = [type(m) for m in msg_mw]
    assert TenantMiddleware in types
    assert AccountMiddleware in types
    assert types.index(TenantMiddleware) < types.index(AccountMiddleware)
```
NOTE: if `list(dp.message.middleware)` does not yield the registered middlewares in this aiogram version, use the concrete list `dp.message.middleware._middlewares` instead (same ordering). Verify which works and keep the one that does.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_menu_and_dispatcher.py::test_tenant_middleware_registered_before_account -v`
Expected: FAIL — TenantMiddleware not registered.

- [ ] **Step 3: Update `app.py`**

In `src/quantuum/bot/app.py` `create_dispatcher`, register `TenantMiddleware` before `AccountMiddleware` on both observers. Replace the two middleware lines:
```python
    dp.message.middleware(AccountMiddleware())
    dp.callback_query.middleware(AccountMiddleware())
```
with:
```python
    from quantuum.bot.middleware.tenant import TenantMiddleware

    dp.message.middleware(TenantMiddleware())
    dp.message.middleware(AccountMiddleware())
    dp.callback_query.middleware(TenantMiddleware())
    dp.callback_query.middleware(AccountMiddleware())
```
(Keep the existing `from quantuum.bot.middleware.account import AccountMiddleware` import at the top.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_menu_and_dispatcher.py -q` then `uv run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/app.py tests/test_menu_and_dispatcher.py
git commit -m "feat: register TenantMiddleware before AccountMiddleware"
```

---

## Task 12: Startup wiring (api lifespan + bootstrap bot) and remove dead get_default_tenant_id hot-path use

**Files:**
- Modify: `src/quantuum/api/app.py` (lifespan also seeds the default bot)
- Test: `tests/test_bootstrap_startup.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bootstrap_startup.py`:
```python
async def test_startup_seeds_default_tenant_bot(client, session):
    from sqlmodel import select

    from quantuum.db.models import TenantBot

    result = await session.execute(select(TenantBot))
    # conftest sets BOT_TOKEN="123:test" -> one bot row seeded by lifespan
    assert any(tb.bot_telegram_id == 123 for tb in result.scalars().all())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bootstrap_startup.py::test_startup_seeds_default_tenant_bot -v`
Expected: FAIL — lifespan only seeds the tenant, not the bot.

- [ ] **Step 3: Update the api lifespan**

In `src/quantuum/api/app.py`, the `_lifespan` currently calls `ensure_default_tenant`. Add the bot seed right after it:
```python
@asynccontextmanager
async def _lifespan(app: FastAPI):
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
    yield
```
and add the import near the existing bootstrap import:
```python
from quantuum.db.bootstrap import ensure_default_tenant, ensure_default_tenant_bot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bootstrap_startup.py -q` then `uv run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Confirm `get_default_tenant_id` is no longer in any request hot path**

Run: `grep -rn "get_default_tenant_id" src/`
Expected: only `domain/tenants.py` (definition), `db/bootstrap.py` (used by `ensure_default_tenant_bot`), and `api/routes/auth.py` (magic-link tenant — acceptable: the public API binds magic-link auth to the default/platform tenant in 2a; per-tenant `tenant_slug` is a later refinement). It must NOT appear in `bot/middleware/account.py` anymore.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/api/app.py tests/test_bootstrap_startup.py
git commit -m "feat: seed default tenant bot on api startup"
```

---

## Task 13: Lint, full suite, polling smoke

**Files:** none (verification)

- [ ] **Step 1: Lint**

Run: `uv run ruff check src tests`
Expected: clean (fix unused imports, e.g. a stray `get_default_tenant_id` import if any remains).

- [ ] **Step 2: Full suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 3: Polling smoke (manual)**

```bash
docker compose build
docker compose -f docker-compose.yml -f docker-compose.polling.yml up -d
docker compose logs --tail=5 bot-worker   # expect bot_polling_started polling_bots=1
```
In Telegram message the bot: `/start` → menu appears (tenant resolved from the DB-backed bot, not the env default). `/profile`, `/blueprint` work as before.
Then `docker compose down`.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint pass for tenancy foundation"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage (2a slice of §4/§8):** `tenant_bots` ✓ (T2), `tenant_roles` ✓ (T2), Tenant tenancy fields ✓ (T2), token encryption ✓ (T1), tenant resolution by bot ✓ (T4/T6), webhook resolves bot from DB ✓ (T9), multi-bot pool runtime ✓ (T7/T10), role helpers ✓ (T4). Master bot / invites / superadmin API / provisioning are **Plan 2b** (not here).
- **Behavior preserved:** the existing single bot keeps working — bootstrap migrates its env token into a `tenant_bots` row, and resolution maps `bot.id` → that row → the default tenant. End users see no change.
- **`get_default_tenant_id` retained** only for: bootstrap (seeding the default bot) and API magic-link tenant binding (a later refinement adds `tenant_slug`). It is removed from the bot middleware hot path.
- **Type consistency:** queue envelope `{"bot_id", "update"}` is produced by `push_update(bot_id, update)` (T8), consumed by `process_one_envelope` (T10) and `webhook` (T9); `build_bots` keys by `bot_telegram_id` matching `Bot.id` and `resolve_tenant_id_by_bot` (T4/T6/T7).
- **aiogram offline-safety:** `Bot(token=...)` and `Bot.id` need no network; tests construct bots and assert `.id` without hitting Telegram.

## Execution Handoff

(Filled in after user picks an execution approach.)
