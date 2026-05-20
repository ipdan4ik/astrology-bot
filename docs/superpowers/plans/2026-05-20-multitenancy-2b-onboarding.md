# Multi-tenancy 2b — Master bot, invites & tenant provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add superadmin-issued invites, a separate master/onboarding Telegram bot, an invite-driven owner-onboarding FSM, and a `provision_tenant` flow (BotFather-fallback only) that spins up new customer tenants end-to-end.

**Architecture:** Builds on Plan 2a (row-level tenancy, tenant resolution by `bot.id`). A dedicated **platform tenant** (`is_platform=true`) owns the **master bot** (env `MASTER_BOT_TOKEN`), driven by a *separate dispatcher* (`create_master_dispatcher`) wired with onboarding handlers only — no astrology. Superadmins (`accounts.is_superadmin=true`, `tenant_id=NULL`) issue `tenant_invites` through `/admin/platform/...`. An owner opens the master-bot deeplink `?start=<code>`, an FSM collects `slug/display_name/default_lang`, and on confirm a provisioning tenant + bot row are created and `arq.provision_tenant` is enqueued. Programmatic bot creation is a stub (`try_programmatic_create → None`) so every tenant takes the fallback path: the master bot asks the owner to paste a BotFather token, validates it via `get_me()`, then `finalize_provisioning` activates the tenant.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3.x, SQLModel, asyncpg, Alembic, Redis 7, arq, pytest+pytest-asyncio+httpx, uv.

**Scope notes (decided with user 2026-05-20):**
- Master bot uses a real second token in dev (`MASTER_BOT_TOKEN`); all logic is unit-tested with mock bots so the token is never required for tests.
- Self-service owner commands (`/tenants`, `/manage`, `/transfer`) are **deferred to Plan 5** (they depend on the admin API). 2b delivers only invite → onboarding → provisioning → fallback-token activation.
- Programmatic Telegram bot creation is **not** attempted (Telegram has no official API). `try_programmatic_create` is a stub returning `None`; the fallback (owner pastes a BotFather token) is the only path.
- **Known limitation (documented, not fixed in 2b):** a newly-provisioned bot becomes `active` in the DB but is picked into the live polling/webhook pool only on `bot-worker` restart. The master bot and the existing default product bot already work live.

---

## File Structure

**New files:**
- `src/quantuum/domain/invites.py` — invite CRUD + usability check.
- `src/quantuum/domain/provisioning.py` — tenant creation, token validation, finalize.
- `src/quantuum/tasks/provision.py` — `provision_tenant` arq task.
- `src/quantuum/api/routes/admin_platform.py` — superadmin endpoints (invites + tenants list).
- `src/quantuum/bot/handlers/master_onboarding.py` — master-bot onboarding FSM.
- `src/quantuum/bot/master_app.py` — `create_master_dispatcher`.
- Test files mirroring each (`tests/test_*.py`).

**Modified files:**
- `src/quantuum/db/models.py` — `TenantInvite` model; `Account.is_superadmin` + nullable `tenant_id`.
- `alembic/versions/<new>.py` — migration.
- `src/quantuum/settings.py` — master bot + superadmin + platform env.
- `src/quantuum/db/bootstrap.py` — `ensure_platform_tenant`, `ensure_master_bot`, `ensure_superadmin`.
- `src/quantuum/domain/tenants.py` — `get_platform_tenant_id`.
- `src/quantuum/auth/jwt_tokens.py` — `sa` claim.
- `src/quantuum/auth/identity.py` — `find_superadmin_by_email`.
- `src/quantuum/api/deps.py` — `require_superadmin`.
- `src/quantuum/api/routes/auth.py` — superadmin-aware magic login.
- `src/quantuum/api/schemas.py` — invite/tenant schemas; `MeOut.tenant_id` optional.
- `src/quantuum/api/app.py` — wire admin router + bootstrap calls.
- `src/quantuum/bot/ui/callbacks.py` — `OwnerOnboardCb`.
- `src/quantuum/tasks/enqueue.py` — `enqueue_provision_tenant`.
- `src/quantuum/tasks/worker.py` — register task + `master_bot` in ctx.
- `src/quantuum/bot/polling.py`, `src/quantuum/bot/runner.py` — two-dispatcher wiring.
- `docker-compose.yml`, `.env.example` — new env vars.

---

## Phase A — Data model & settings

### Task 1: TenantInvite model + Account superadmin fields + migration

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/a2b1c0d9e8f7_invites_and_superadmin.py`
- Test: `tests/test_db_models.py` (append), `tests/test_invites_model.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_invites_model.py`:

```python
from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountIdentity, TenantInvite


async def test_create_invite_row(session):
    inv = TenantInvite(code="abc123", tier="basic", max_uses=3, expires_at=utcnow() + timedelta(days=1))
    session.add(inv)
    await session.commit()
    await session.refresh(inv)
    assert inv.id is not None
    assert inv.used_count == 0
    assert inv.status == "active"


async def test_superadmin_account_has_null_tenant(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()
    await session.refresh(acc)
    assert acc.tenant_id is None
    assert acc.is_superadmin is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_invites_model.py -v`
Expected: FAIL — `ImportError` / `AttributeError` (no `TenantInvite`, `Account.is_superadmin`).

- [ ] **Step 3: Implement the model changes**

In `src/quantuum/db/models.py`, change `Account`:

```python
class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    is_superadmin: bool = False
    status: str = "active"  # active|disabled
    preferred_lang: str | None = None
    last_seen_at: datetime | None = _dt_field(default=None)
    created_at: datetime = _dt_field(default_factory=utcnow)
```

Add `TenantInvite` after `TenantRole`:

```python
class TenantInvite(SQLModel, table=True):
    __tablename__ = "tenant_invites"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)
    created_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    tier: str = "basic"  # basic|vip
    max_uses: int = 1
    used_count: int = 0
    expires_at: datetime | None = _dt_field(default=None)
    status: str = "active"  # active|used|expired|revoked
    preset_slug: str | None = None
    preset_display_name: str | None = None
    preset_username: str | None = None
    preset_default_lang: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    used_at: datetime | None = _dt_field(default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_invites_model.py -v`
Expected: PASS (tests create tables from models via `SQLModel.metadata.create_all`).

- [ ] **Step 5: Write the Alembic migration**

Create `alembic/versions/a2b1c0d9e8f7_invites_and_superadmin.py`:

```python
"""invites table + accounts superadmin/nullable tenant_id

Revision ID: a2b1c0d9e8f7
Revises: 333649f38ecf
Create Date: 2026-05-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "a2b1c0d9e8f7"
down_revision: Union[str, Sequence[str], None] = "333649f38ecf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("tier", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("preset_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("preset_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("preset_username", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("preset_default_lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_invites_code"), "tenant_invites", ["code"], unique=True)
    op.add_column(
        "accounts",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.alter_column("accounts", "tenant_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("accounts", "tenant_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("accounts", "is_superadmin")
    op.drop_index(op.f("ix_tenant_invites_code"), table_name="tenant_invites")
    op.drop_table("tenant_invites")
```

- [ ] **Step 6: Verify migration applies with no drift**

Run: `uv run alembic upgrade head`
Expected: applies cleanly (DB at `172.30.0.2` per conftest env).
Run: `uv run alembic check`
Expected: "No new upgrade operations detected." (model and migration agree). If `alembic check` is unavailable, run `uv run alembic revision --autogenerate -m _drift_check`, confirm the generated `upgrade()` body is empty, then delete the file.

- [ ] **Step 7: Run full suite + commit**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass. (Existing tests are unaffected: nullable `tenant_id` and the new column are additive.)

```bash
git add src/quantuum/db/models.py alembic/versions/a2b1c0d9e8f7_invites_and_superadmin.py tests/test_invites_model.py
git commit -m "feat(2b): TenantInvite model + accounts superadmin/nullable tenant_id + migration"
```

---

### Task 2: Settings — master bot, superadmin, platform tenant

**Files:**
- Modify: `src/quantuum/settings.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings.py`:

```python
def test_settings_have_2b_defaults():
    from quantuum.settings import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.master_bot_token == ""
    assert s.master_bot_username == ""
    assert s.bootstrap_superadmin_email == ""
    assert s.platform_tenant_slug == "platform"
    assert s.platform_tenant_name == "Quantuum Platform"
    get_settings.cache_clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py::test_settings_have_2b_defaults -v`
Expected: FAIL — `AttributeError: master_bot_token`.

- [ ] **Step 3: Implement**

In `src/quantuum/settings.py`, add fields to `Settings` (after `default_bot_transport`):

```python
    master_bot_token: str = ""
    master_bot_username: str = ""
    bootstrap_superadmin_email: str = ""
    platform_tenant_slug: str = "platform"
    platform_tenant_name: str = "Quantuum Platform"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/settings.py tests/test_settings.py
git commit -m "feat(2b): add master bot / superadmin / platform tenant settings"
```

---

## Phase B — Superadmin identity & bootstrap

### Task 3: Bootstrap platform tenant, master bot, superadmin + platform helper

**Files:**
- Modify: `src/quantuum/db/bootstrap.py`, `src/quantuum/domain/tenants.py`
- Test: `tests/test_bootstrap_platform.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_platform.py`:

```python
from sqlmodel import select

from quantuum.common.crypto import decrypt_token
from quantuum.db.bootstrap import ensure_master_bot, ensure_platform_tenant, ensure_superadmin
from quantuum.db.models import Account, AccountIdentity, Tenant, TenantBot
from quantuum.domain.tenants import get_platform_tenant_id
from quantuum.settings import get_settings


async def test_ensure_platform_tenant_idempotent(session):
    t1 = await ensure_platform_tenant(session)
    t2 = await ensure_platform_tenant(session)
    assert t1.id == t2.id
    assert t1.is_platform is True
    assert t1.slug == "platform"
    assert await get_platform_tenant_id(session) == t1.id


async def test_ensure_master_bot_creates_row(session, monkeypatch):
    monkeypatch.setenv("MASTER_BOT_TOKEN", "888:masters")
    monkeypatch.setenv("MASTER_BOT_USERNAME", "quantuum_master_bot")
    get_settings.cache_clear()

    await ensure_master_bot(session)
    await ensure_master_bot(session)  # idempotent

    platform_id = await get_platform_tenant_id(session)
    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == platform_id))
    bots = result.scalars().all()
    assert len(bots) == 1
    assert bots[0].bot_telegram_id == 888
    assert bots[0].bot_username == "quantuum_master_bot"
    assert decrypt_token(bots[0].bot_token_enc) == "888:masters"
    get_settings.cache_clear()


async def test_ensure_master_bot_noop_without_token(session, monkeypatch):
    monkeypatch.setenv("MASTER_BOT_TOKEN", "")
    get_settings.cache_clear()
    await ensure_master_bot(session)
    platform_id = await get_platform_tenant_id(session)
    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == platform_id))
    assert result.scalars().first() is None
    get_settings.cache_clear()


async def test_ensure_superadmin_creates_account(session, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_EMAIL", "root@quantuum.example")
    get_settings.cache_clear()

    await ensure_superadmin(session)
    await ensure_superadmin(session)  # idempotent

    result = await session.execute(
        select(Account).where(Account.is_superadmin == True)  # noqa: E712
    )
    admins = result.scalars().all()
    assert len(admins) == 1
    assert admins[0].tenant_id is None
    ident = await session.execute(
        select(AccountIdentity).where(AccountIdentity.email == "root@quantuum.example")
    )
    assert ident.scalar_one().provider == "magic_link"
    get_settings.cache_clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bootstrap_platform.py -v`
Expected: FAIL — `ImportError` (functions/helper don't exist).

- [ ] **Step 3: Add `get_platform_tenant_id`**

In `src/quantuum/domain/tenants.py`, add `Tenant` to the import and append:

```python
async def get_platform_tenant_id(session) -> int | None:
    result = await session.execute(select(Tenant.id).where(Tenant.is_platform == True))  # noqa: E712
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Implement bootstrap functions**

In `src/quantuum/db/bootstrap.py`, update imports and append:

```python
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountIdentity, Tenant, TenantBot


async def ensure_platform_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(
        select(Tenant).where(Tenant.slug == settings.platform_tenant_slug)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            slug=settings.platform_tenant_slug,
            display_name=settings.platform_tenant_name,
            is_platform=True,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant


async def ensure_master_bot(session) -> None:
    """Migrate env MASTER_BOT_TOKEN into the platform tenant's tenant_bots row (idempotent)."""
    settings = get_settings()
    token = settings.master_bot_token
    if not token:
        return
    bot_id = int(token.split(":")[0])
    existing = await session.execute(
        select(TenantBot).where(TenantBot.bot_telegram_id == bot_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    platform = await ensure_platform_tenant(session)
    session.add(
        TenantBot(
            tenant_id=platform.id,
            bot_telegram_id=bot_id,
            bot_username=settings.master_bot_username or None,
            bot_token_enc=encrypt_token(token),
            transport=settings.default_bot_transport,
            webhook_secret_path=f"master-{bot_id}",
        )
    )
    await session.commit()


async def ensure_superadmin(session) -> None:
    """Create the bootstrap superadmin account from env (idempotent, env-gated)."""
    settings = get_settings()
    email = settings.bootstrap_superadmin_email
    if not email:
        return
    existing = await session.execute(
        select(AccountIdentity).where(
            AccountIdentity.provider == "magic_link", AccountIdentity.email == email
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    account = Account(tenant_id=None, is_superadmin=True)
    session.add(account)
    await session.flush()
    session.add(
        AccountIdentity(
            account_id=account.id, provider="magic_link", email=email, verified_at=utcnow()
        )
    )
    await session.commit()
```

Note: the existing `from quantuum.db.models import Tenant, TenantBot` line must be widened to include `Account, AccountIdentity` (merge with the import above; do not duplicate).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_bootstrap_platform.py -v`
Expected: PASS.

- [ ] **Step 6: Wire bootstrap into app/polling/runner lifespans**

In `src/quantuum/api/app.py` `_lifespan`, extend:

```python
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_superadmin(session)
```

Update the import: `from quantuum.db.bootstrap import (ensure_default_tenant, ensure_default_tenant_bot, ensure_master_bot, ensure_platform_tenant, ensure_superadmin)`.

In `src/quantuum/bot/polling.py` and `src/quantuum/bot/runner.py`, in each `run()` after the existing `ensure_default_*` calls and inside the same `async with ... session` block, add:

```python
        await ensure_platform_tenant(session)
        await ensure_master_bot(session)
```

and widen their bootstrap imports accordingly. (These two also need master/customer split — done in Phase F; this step only adds the bootstrap calls.)

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass.

```bash
git add src/quantuum/db/bootstrap.py src/quantuum/domain/tenants.py src/quantuum/api/app.py src/quantuum/bot/polling.py src/quantuum/bot/runner.py tests/test_bootstrap_platform.py
git commit -m "feat(2b): bootstrap platform tenant, master bot, superadmin + platform helper"
```

---

### Task 4: JWT `sa` claim, require_superadmin, superadmin-aware magic login

**Files:**
- Modify: `src/quantuum/auth/jwt_tokens.py`, `src/quantuum/auth/identity.py`, `src/quantuum/api/deps.py`, `src/quantuum/api/routes/auth.py`, `src/quantuum/api/schemas.py`
- Test: `tests/test_jwt_tokens.py` (append), `tests/test_identity.py` (append), `tests/test_api_auth.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jwt_tokens.py`:

```python
def test_access_token_carries_superadmin_claim():
    from quantuum.auth.jwt_tokens import issue_access_token, verify_access_token

    tok = issue_access_token(1, None, True)
    claims = verify_access_token(tok)
    assert claims["sa"] is True
    assert claims["tid"] is None

    tok2 = issue_access_token(2, 5)
    claims2 = verify_access_token(tok2)
    assert claims2["sa"] is False
    assert claims2["tid"] == 5
```

Append to `tests/test_identity.py` (create the file if it only tests other things; add this test):

```python
async def test_find_superadmin_by_email(session):
    from quantuum.auth.identity import find_superadmin_by_email
    from quantuum.db.models import Account, AccountIdentity

    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="sa@x.com"))
    await session.commit()

    found = await find_superadmin_by_email(session, "sa@x.com")
    assert found is not None and found.id == acc.id
    assert await find_superadmin_by_email(session, "nobody@x.com") is None
```

Append to `tests/test_api_auth.py`:

```python
async def test_superadmin_magic_login_issues_sa_token(client, session, monkeypatch):
    from quantuum.auth import jwt_tokens, magic_link
    from quantuum.db.models import Account, AccountIdentity

    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()

    async def fake_send(to_email, link):
        return None

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)
    token = await magic_link.create_magic_token("root@x.com")
    r = await client.get(f"/auth/magic/consume?token={token}")
    assert r.status_code == 200
    claims = jwt_tokens.verify_access_token(r.json()["access_token"])
    assert claims["sa"] is True
    assert claims["tid"] is None
```

(Use the same `client` fixture already defined in `tests/test_api_auth.py`; add a `session` param — it is provided transitively because `default_tenant` already uses it, but declare `session` explicitly in the test signature.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jwt_tokens.py::test_access_token_carries_superadmin_claim tests/test_identity.py::test_find_superadmin_by_email tests/test_api_auth.py::test_superadmin_magic_login_issues_sa_token -v`
Expected: FAIL.

- [ ] **Step 3: Implement JWT change**

In `src/quantuum/auth/jwt_tokens.py`, replace `issue_access_token`:

```python
def issue_access_token(account_id: int, tenant_id: int | None, is_superadmin: bool = False) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": str(account_id),
        "tid": tenant_id,
        "sa": is_superadmin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=_ALG)
```

- [ ] **Step 4: Implement `find_superadmin_by_email`**

In `src/quantuum/auth/identity.py`, append:

```python
async def find_superadmin_by_email(session, email: str) -> Account | None:
    result = await session.execute(
        select(AccountIdentity)
        .join(Account, Account.id == AccountIdentity.account_id)
        .where(
            AccountIdentity.provider == "magic_link",
            AccountIdentity.email == email,
            Account.is_superadmin == True,  # noqa: E712
        )
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        return None
    return await session.get(Account, identity.account_id)
```

- [ ] **Step 5: Implement `require_superadmin`**

In `src/quantuum/api/deps.py`, append:

```python
async def require_superadmin(account: Account = Depends(current_account)) -> Account:
    if not account.is_superadmin:
        raise HTTPException(status_code=403, detail="superadmin required")
    return account
```

- [ ] **Step 6: Update magic login + refresh + MeOut**

In `src/quantuum/api/schemas.py`, change `MeOut`:

```python
class MeOut(BaseModel):
    account_id: int
    tenant_id: int | None
```

In `src/quantuum/api/routes/auth.py`, update imports and `magic_consume`/`refresh`:

```python
from quantuum.auth.identity import find_or_create_account_by_email, find_superadmin_by_email
```

```python
@router.get("/magic/consume", response_model=TokenOut)
async def magic_consume(token: str, session: AsyncSession = Depends(get_session)) -> TokenOut:
    email = await magic_link.consume_magic_token(token)
    if email is None:
        raise HTTPException(status_code=400, detail="invalid or expired token")
    account = await find_superadmin_by_email(session, email)
    if account is None:
        tenant_id = await get_default_tenant_id(session)
        account = await find_or_create_account_by_email(session, tenant_id=tenant_id, email=email)
    access = jwt_tokens.issue_access_token(account.id, account.tenant_id, account.is_superadmin)
    refresh = await jwt_tokens.issue_refresh_token(session, account.id)
    return TokenOut(access_token=access, refresh_token=refresh)
```

```python
@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        account = await jwt_tokens.consume_refresh_token(session, body.refresh_token)
    except NotFoundError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    access = jwt_tokens.issue_access_token(account.id, account.tenant_id, account.is_superadmin)
    return TokenOut(access_token=access, refresh_token=body.refresh_token)
```

- [ ] **Step 7: Run tests + suite + commit**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass.

```bash
git add src/quantuum/auth/jwt_tokens.py src/quantuum/auth/identity.py src/quantuum/api/deps.py src/quantuum/api/routes/auth.py src/quantuum/api/schemas.py tests/test_jwt_tokens.py tests/test_identity.py tests/test_api_auth.py
git commit -m "feat(2b): sa JWT claim, require_superadmin, superadmin-aware magic login"
```

---

## Phase C — Invites domain & superadmin API

### Task 5: Invites domain service

**Files:**
- Create: `src/quantuum/domain/invites.py`
- Test: `tests/test_invites_domain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_invites_domain.py`:

```python
from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.domain.invites import (
    create_invite,
    get_invite_by_code,
    invite_is_usable,
    list_invites,
    revoke_invite,
)


async def test_create_and_get_invite(session):
    inv = await create_invite(session, created_by_account_id=None, tier="vip", max_uses=2)
    assert inv.code
    assert inv.tier == "vip"
    fetched = await get_invite_by_code(session, inv.code)
    assert fetched is not None and fetched.id == inv.id


async def test_list_invites_newest_first(session):
    a = await create_invite(session, created_by_account_id=None)
    b = await create_invite(session, created_by_account_id=None)
    rows = await list_invites(session)
    assert [r.id for r in rows][:2] == [b.id, a.id]


async def test_revoke_invite(session):
    inv = await create_invite(session, created_by_account_id=None)
    revoked = await revoke_invite(session, inv.id)
    assert revoked.status == "revoked"
    assert await revoke_invite(session, 999999) is None


def test_invite_is_usable():
    now = utcnow()
    active = type("I", (), {"status": "active", "expires_at": None, "used_count": 0, "max_uses": 1})()
    assert invite_is_usable(active, now=now) is True

    expired = type("I", (), {"status": "active", "expires_at": now - timedelta(hours=1), "used_count": 0, "max_uses": 1})()
    assert invite_is_usable(expired, now=now) is False

    exhausted = type("I", (), {"status": "active", "expires_at": None, "used_count": 1, "max_uses": 1})()
    assert invite_is_usable(exhausted, now=now) is False

    revoked = type("I", (), {"status": "revoked", "expires_at": None, "used_count": 0, "max_uses": 1})()
    assert invite_is_usable(revoked, now=now) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_invites_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: quantuum.domain.invites`.

- [ ] **Step 3: Implement**

Create `src/quantuum/domain/invites.py`:

```python
from datetime import datetime

from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.ids import url_safe_token
from quantuum.db.models import TenantInvite


async def create_invite(
    session,
    *,
    created_by_account_id: int | None,
    tier: str = "basic",
    max_uses: int = 1,
    expires_at: datetime | None = None,
    preset_slug: str | None = None,
    preset_display_name: str | None = None,
    preset_username: str | None = None,
    preset_default_lang: str | None = None,
) -> TenantInvite:
    invite = TenantInvite(
        code=url_safe_token(16),
        created_by_account_id=created_by_account_id,
        tier=tier,
        max_uses=max_uses,
        expires_at=expires_at,
        preset_slug=preset_slug,
        preset_display_name=preset_display_name,
        preset_username=preset_username,
        preset_default_lang=preset_default_lang,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def list_invites(session) -> list[TenantInvite]:
    result = await session.execute(select(TenantInvite).order_by(TenantInvite.id.desc()))
    return list(result.scalars().all())


async def get_invite_by_code(session, code: str) -> TenantInvite | None:
    result = await session.execute(select(TenantInvite).where(TenantInvite.code == code))
    return result.scalar_one_or_none()


async def revoke_invite(session, invite_id: int) -> TenantInvite | None:
    invite = await session.get(TenantInvite, invite_id)
    if invite is None:
        return None
    invite.status = "revoked"
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


def invite_is_usable(invite, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if invite.status != "active":
        return False
    if invite.expires_at is not None and invite.expires_at < now:
        return False
    if invite.used_count >= invite.max_uses:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_invites_domain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/invites.py tests/test_invites_domain.py
git commit -m "feat(2b): invites domain service (create/list/get/revoke/usable)"
```

---

### Task 6: Superadmin API — invites + tenants list

**Files:**
- Create: `src/quantuum/api/routes/admin_platform.py`
- Modify: `src/quantuum/api/schemas.py`, `src/quantuum/api/app.py`
- Test: `tests/test_api_admin_platform.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_admin_platform.py`:

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import Account, AccountIdentity


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def sa_headers(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, None, True)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_create_and_list_invite(client, sa_headers):
    r = await client.post(
        "/admin/platform/invites",
        json={"tier": "basic", "max_uses": 2},
        headers=sa_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["code"]
    assert body["deeplink"].endswith(body["code"])
    assert body["tier"] == "basic"

    lst = await client.get("/admin/platform/invites", headers=sa_headers)
    assert lst.status_code == 200
    assert any(i["code"] == body["code"] for i in lst.json())


async def test_revoke_invite(client, sa_headers):
    created = await client.post("/admin/platform/invites", json={}, headers=sa_headers)
    invite_id = created.json()["id"]
    r = await client.post(f"/admin/platform/invites/{invite_id}/revoke", headers=sa_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


async def test_list_tenants(client, sa_headers, default_tenant):
    r = await client.get("/admin/platform/tenants", headers=sa_headers)
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()}
    assert "default" in slugs


async def test_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/invites", headers=customer_headers)
    assert r.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_admin_platform.py -v`
Expected: FAIL — 404 on routes (router not wired).

- [ ] **Step 3: Add schemas**

In `src/quantuum/api/schemas.py`, add `from datetime import date, datetime, time` (widen existing import) and append:

```python
class InviteCreateIn(BaseModel):
    tier: str = "basic"
    max_uses: int = 1
    expires_at: datetime | None = None
    preset_slug: str | None = None
    preset_display_name: str | None = None
    preset_username: str | None = None
    preset_default_lang: str | None = None


class InviteOut(BaseModel):
    id: int
    code: str
    tier: str
    max_uses: int
    used_count: int
    status: str
    deeplink: str


class TenantOut(BaseModel):
    id: int
    slug: str
    display_name: str
    tier: str
    status: str
    is_platform: bool
```

- [ ] **Step 4: Implement routes**

Create `src/quantuum/api/routes/admin_platform.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_superadmin
from quantuum.api.schemas import InviteCreateIn, InviteOut, TenantOut
from quantuum.db.models import Account, Tenant, TenantInvite
from quantuum.domain.invites import create_invite, list_invites, revoke_invite
from quantuum.settings import get_settings

router = APIRouter(prefix="/admin/platform", tags=["admin-platform"])


def _invite_out(invite: TenantInvite) -> InviteOut:
    username = get_settings().master_bot_username
    deeplink = f"https://t.me/{username}?start={invite.code}"
    return InviteOut(
        id=invite.id,
        code=invite.code,
        tier=invite.tier,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        status=invite.status,
        deeplink=deeplink,
    )


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite_route(
    body: InviteCreateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    invite = await create_invite(
        session,
        created_by_account_id=admin.id,
        tier=body.tier,
        max_uses=body.max_uses,
        expires_at=body.expires_at,
        preset_slug=body.preset_slug,
        preset_display_name=body.preset_display_name,
        preset_username=body.preset_username,
        preset_default_lang=body.preset_default_lang,
    )
    return _invite_out(invite)


@router.get("/invites", response_model=list[InviteOut])
async def list_invites_route(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[InviteOut]:
    return [_invite_out(i) for i in await list_invites(session)]


@router.post("/invites/{invite_id}/revoke", response_model=InviteOut)
async def revoke_invite_route(
    invite_id: int,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    invite = await revoke_invite(session, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="invite not found")
    return _invite_out(invite)


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants_route(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[TenantOut]:
    result = await session.execute(select(Tenant).order_by(Tenant.id))
    return [
        TenantOut(
            id=t.id,
            slug=t.slug,
            display_name=t.display_name,
            tier=t.tier,
            status=t.status,
            is_platform=t.is_platform,
        )
        for t in result.scalars().all()
    ]
```

- [ ] **Step 5: Wire router**

In `src/quantuum/api/app.py`, import and include:

```python
from quantuum.api.routes import admin_platform, auth, health, me, webhook
```
```python
    app.include_router(admin_platform.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_api_admin_platform.py -v`
Expected: PASS.

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/api/routes/admin_platform.py src/quantuum/api/schemas.py src/quantuum/api/app.py tests/test_api_admin_platform.py
git commit -m "feat(2b): superadmin API for invites + tenants list"
```

---

## Phase D — Provisioning domain & task

### Task 7: Provisioning — create tenant from onboarding

**Files:**
- Create: `src/quantuum/domain/provisioning.py`
- Test: `tests/test_provisioning.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_provisioning.py`:

```python
from sqlmodel import select

from quantuum.db.models import Tenant, TenantBot
from quantuum.domain.invites import create_invite
from quantuum.domain.provisioning import create_tenant_from_onboarding, try_programmatic_create


async def test_try_programmatic_create_returns_none():
    assert await try_programmatic_create(slug="x", display_name="X") is None


async def test_create_tenant_from_onboarding(session):
    invite = await create_invite(session, created_by_account_id=None, tier="basic", max_uses=1)
    tenant = await create_tenant_from_onboarding(
        session,
        invite=invite,
        slug="acme",
        display_name="Acme Astro",
        default_lang="ru",
        owner_tg_id=12345,
        owner_chat_id=12345,
    )
    assert tenant.status == "provisioning"
    assert tenant.tier == "basic"
    assert tenant.owner_tg_id == "12345"
    assert tenant.owner_chat_id == "12345"

    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant.id))
    tb = result.scalar_one()
    assert tb.status == "provisioning"
    assert tb.webhook_secret_path
    assert tb.bot_telegram_id is None

    await session.refresh(invite)
    assert invite.used_count == 1
    assert invite.status == "used"


async def test_create_tenant_multiuse_invite_stays_active(session):
    invite = await create_invite(session, created_by_account_id=None, max_uses=2)
    await create_tenant_from_onboarding(
        session, invite=invite, slug="a1", display_name="A1",
        default_lang="ru", owner_tg_id=1, owner_chat_id=1,
    )
    await session.refresh(invite)
    assert invite.used_count == 1
    assert invite.status == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provisioning.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/quantuum/domain/provisioning.py`:

```python
from quantuum.common.datetime import utcnow
from quantuum.common.ids import url_safe_token
from quantuum.db.models import Tenant, TenantBot, TenantInvite


async def try_programmatic_create(*, slug: str, display_name: str) -> str | None:
    """MVP: Telegram has no official API to create bots programmatically.

    Always returns None so provisioning takes the BotFather-fallback path
    (owner pastes a token into the master bot). This is the seam where a future
    programmatic-creation integration would return a freshly minted token.
    """
    return None


async def create_tenant_from_onboarding(
    session,
    *,
    invite: TenantInvite,
    slug: str,
    display_name: str,
    default_lang: str,
    owner_tg_id: int | str,
    owner_chat_id: int | str,
    transport: str = "polling",
) -> Tenant:
    """Atomically create a provisioning tenant + bot row and consume one invite use."""
    tenant = Tenant(
        slug=slug,
        display_name=display_name,
        tier=invite.tier,
        status="provisioning",
        owner_tg_id=str(owner_tg_id),
        owner_chat_id=str(owner_chat_id),
    )
    session.add(tenant)
    await session.flush()
    session.add(
        TenantBot(
            tenant_id=tenant.id,
            bot_token_enc=b"",
            transport=transport,
            webhook_secret_path=url_safe_token(16),
            status="provisioning",
        )
    )
    invite.used_count += 1
    if invite.used_count >= invite.max_uses:
        invite.status = "used"
        invite.used_at = utcnow()
    session.add(invite)
    await session.commit()
    await session.refresh(tenant)
    return tenant
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_provisioning.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/provisioning.py tests/test_provisioning.py
git commit -m "feat(2b): provisioning — create_tenant_from_onboarding + stub programmatic create"
```

---

### Task 8: Provisioning — validate token & finalize

**Files:**
- Modify: `src/quantuum/domain/provisioning.py`
- Test: `tests/test_provisioning.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_provisioning.py`:

```python
async def test_finalize_provisioning_activates_tenant(session):
    from quantuum.common.crypto import decrypt_token
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding, finalize_provisioning
    from quantuum.domain.tenants import account_has_role
    from quantuum.db.models import Account

    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )

    tb = await finalize_provisioning(
        session,
        tenant_id=tenant.id,
        token="900:newbottoken",
        bot_telegram_id=900,
        bot_username="zen_bot",
        default_lang="ru",
    )
    assert tb.status == "active"
    assert tb.bot_telegram_id == 900
    assert tb.bot_username == "zen_bot"
    assert decrypt_token(tb.bot_token_enc) == "900:newbottoken"

    await session.refresh(tenant)
    assert tenant.status == "active"
    assert tenant.primary_owner_account_id is not None

    owner = await session.get(Account, tenant.primary_owner_account_id)
    assert owner.tenant_id == tenant.id
    assert await account_has_role(session, tenant_id=tenant.id, account_id=owner.id, role="owner")


async def test_validate_bot_token_rejects_garbage(monkeypatch):
    from quantuum.domain import provisioning

    assert await provisioning.validate_bot_token("not-a-token") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provisioning.py::test_finalize_provisioning_activates_tenant tests/test_provisioning.py::test_validate_bot_token_rejects_garbage -v`
Expected: FAIL — functions missing.

- [ ] **Step 3: Implement**

In `src/quantuum/domain/provisioning.py`, add imports and functions:

```python
from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.crypto import encrypt_token
from quantuum.domain.tenants import grant_role
```

```python
async def validate_bot_token(token: str) -> tuple[int, str] | None:
    """Validate a Telegram bot token via get_me(). Returns (bot_id, username) or None."""
    from aiogram import Bot
    from aiogram.utils.token import TokenValidationError, validate_token

    try:
        validate_token(token)
    except TokenValidationError:
        return None
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return me.id, me.username
    except Exception:
        return None
    finally:
        await bot.session.close()


async def seed_tenant_defaults(session, *, tenant_id: int, default_lang: str) -> None:
    """Placeholder seam: per-tenant languages/config land in the i18n plan (Plan 5)."""
    return None


async def finalize_provisioning(
    session,
    *,
    tenant_id: int,
    token: str,
    bot_telegram_id: int,
    bot_username: str | None,
    default_lang: str,
) -> TenantBot:
    """Activate a provisioning tenant: save the validated token, create the owner
    account in the new tenant, grant the owner role, and flip statuses to active."""
    tenant = await session.get(Tenant, tenant_id)
    result = await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant_id))
    tenant_bot = result.scalars().first()

    owner_account = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=str(tenant.owner_tg_id)
    )
    await grant_role(session, tenant_id=tenant_id, account_id=owner_account.id, role="owner")

    tenant_bot.bot_token_enc = encrypt_token(token)
    tenant_bot.bot_telegram_id = bot_telegram_id
    tenant_bot.bot_username = bot_username
    tenant_bot.status = "active"
    tenant_bot.updated_at = utcnow()
    tenant.primary_owner_account_id = owner_account.id
    tenant.status = "active"
    session.add(tenant_bot)
    session.add(tenant)
    await seed_tenant_defaults(session, tenant_id=tenant_id, default_lang=default_lang)
    await session.commit()
    await session.refresh(tenant_bot)
    return tenant_bot
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_provisioning.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/domain/provisioning.py tests/test_provisioning.py
git commit -m "feat(2b): provisioning — validate_bot_token + finalize_provisioning"
```

---

### Task 9: provision_tenant arq task + enqueue + worker registration

**Files:**
- Create: `src/quantuum/tasks/provision.py`
- Modify: `src/quantuum/tasks/enqueue.py`, `src/quantuum/tasks/worker.py`
- Test: `tests/test_task_provision.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_provision.py`:

```python
from unittest.mock import AsyncMock

from quantuum.db.models import Tenant
from quantuum.domain.invites import create_invite
from quantuum.domain.provisioning import create_tenant_from_onboarding
from quantuum.tasks.provision import provision_tenant


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


async def test_provision_falls_back_to_manual_token(session):
    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="fb", display_name="FB",
        default_lang="ru", owner_tg_id=42, owner_chat_id=42,
    )
    master_bot = AsyncMock()
    ctx = {"sessionmaker": _Maker(session), "master_bot": master_bot}

    await provision_tenant(ctx, tenant.id)

    await session.refresh(tenant)
    assert tenant.status == "awaiting_manual_token"
    master_bot.send_message.assert_awaited_once()
    chat_id, _text = master_bot.send_message.await_args.args
    assert chat_id == 42


async def test_provision_unknown_tenant_is_safe(session):
    ctx = {"sessionmaker": _Maker(session), "master_bot": AsyncMock()}
    await provision_tenant(ctx, 999999)  # no exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_provision.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement task**

Create `src/quantuum/tasks/provision.py`:

```python
from quantuum.db.models import Tenant
from quantuum.domain.provisioning import try_programmatic_create
from quantuum.logging_setup import get_logger

logger = get_logger("tasks.provision")

_MANUAL_TOKEN_PROMPT = (
    "Автосоздание бота недоступно. Создай нового бота через @BotFather "
    "и пришли сюда его токен одним сообщением."
)


async def provision_tenant(ctx, tenant_id: int) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            logger.warning("provision_unknown_tenant", tenant_id=tenant_id)
            return
        token = await try_programmatic_create(slug=tenant.slug, display_name=tenant.display_name)
        if token is None:
            tenant.status = "awaiting_manual_token"
            session.add(tenant)
            await session.commit()
            master_bot = ctx.get("master_bot")
            if master_bot is not None and tenant.owner_chat_id:
                await master_bot.send_message(int(tenant.owner_chat_id), _MANUAL_TOKEN_PROMPT)
            logger.info("provision_awaiting_manual_token", tenant_id=tenant_id)
            return
        # Programmatic path is not used in MVP (try_programmatic_create always returns None).
        logger.info("provision_programmatic_unsupported", tenant_id=tenant_id)
```

- [ ] **Step 4: Add enqueue helper**

In `src/quantuum/tasks/enqueue.py`, append:

```python
async def enqueue_provision_tenant(tenant_id: int) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("provision_tenant", tenant_id)
```

- [ ] **Step 5: Register in worker + add master_bot to ctx**

In `src/quantuum/tasks/worker.py`, update:

```python
from quantuum.tasks.blueprint import blueprint_generate
from quantuum.tasks.provision import provision_tenant


async def startup(ctx) -> None:
    configure_logging()
    settings = get_settings()
    ctx["sessionmaker"] = get_sessionmaker()
    ctx["bot"] = Bot(token=settings.bot_token) if settings.bot_token else None
    ctx["master_bot"] = Bot(token=settings.master_bot_token) if settings.master_bot_token else None


async def shutdown(ctx) -> None:
    for key in ("bot", "master_bot"):
        bot: Bot = ctx.get(key)
        if bot is not None:
            await bot.session.close()


class WorkerSettings:
    functions = [blueprint_generate, provision_tenant]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_task_provision.py -v`
Expected: PASS.

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/tasks/provision.py src/quantuum/tasks/enqueue.py src/quantuum/tasks/worker.py tests/test_task_provision.py
git commit -m "feat(2b): provision_tenant arq task + enqueue + worker master_bot ctx"
```

---

## Phase E — Master bot

### Task 10: OwnerOnboardCb + master onboarding FSM (start + collect)

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py`
- Create: `src/quantuum/bot/handlers/master_onboarding.py`
- Test: `tests/test_master_onboarding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_master_onboarding.py`:

```python
from quantuum.bot.handlers.master_onboarding import slug_is_available
from quantuum.domain.tenants import get_default_tenant_id


async def test_slug_is_available(session, default_tenant):
    assert await slug_is_available(session, "brand-new") is True
    assert await slug_is_available(session, "default") is False


def test_owner_onboard_callback_roundtrip():
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    packed = OwnerOnboardCb(action="confirm").pack()
    assert OwnerOnboardCb.unpack(packed).action == "confirm"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_master_onboarding.py -v`
Expected: FAIL — module/callback missing.

- [ ] **Step 3: Add callback**

In `src/quantuum/bot/ui/callbacks.py`, append:

```python
class OwnerOnboardCb(CallbackData, prefix="own"):
    action: str  # confirm | cancel
```

- [ ] **Step 4: Implement the start + collection FSM**

Create `src/quantuum/bot/handlers/master_onboarding.py`:

```python
from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlmodel import select

from quantuum.bot.ui.callbacks import OwnerOnboardCb
from quantuum.bot.ui.keyboards import cancel_kb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.invites import get_invite_by_code, invite_is_usable

router = Router()


class OwnerOnboarding(StatesGroup):
    slug = State()
    display_name = State()
    default_lang = State()
    confirm = State()


class ManualToken(StatesGroup):
    awaiting = State()


async def slug_is_available(session, slug: str) -> bool:
    result = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
    return result.scalar_one_or_none() is None


def confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Создать бота", callback_data=OwnerOnboardCb(action="confirm").pack()))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data=OwnerOnboardCb(action="cancel").pack()))
    return builder.as_markup()


@router.message(CommandStart(deep_link=True))
async def on_start_with_code(message: Message, command: CommandObject, state: FSMContext) -> None:
    code = (command.args or "").strip()
    async with get_sessionmaker()() as session:
        invite = await get_invite_by_code(session, code)
    if invite is None or not invite_is_usable(invite):
        await message.answer("Приглашение недействительно или истекло.")
        return
    await state.set_state(OwnerOnboarding.slug)
    await state.update_data(invite_id=invite.id, default_lang=invite.preset_default_lang or "ru")
    prefill = f" (предложено: {invite.preset_slug})" if invite.preset_slug else ""
    await message.answer(
        f"Добро пожаловать! Давай создадим бота. Введи slug тенанта (латиница, без пробелов){prefill}:",
        reply_markup=cancel_kb(),
    )


@router.message(CommandStart(deep_link=False))
async def on_plain_start(message: Message) -> None:
    await message.answer("Это бот онбординга платформы. Открой ссылку-приглашение, чтобы создать своего бота.")


@router.message(OwnerOnboarding.slug)
async def on_slug(message: Message, state: FSMContext) -> None:
    slug = (message.text or "").strip().lower()
    if not slug or " " in slug:
        await message.answer("Slug не должен быть пустым или содержать пробелы. Попробуй ещё раз:")
        return
    async with get_sessionmaker()() as session:
        if not await slug_is_available(session, slug):
            await message.answer("Этот slug уже занят. Введи другой:")
            return
    await state.update_data(slug=slug)
    await state.set_state(OwnerOnboarding.display_name)
    await message.answer("Отображаемое имя продукта (например «Acme Astro»):")


@router.message(OwnerOnboarding.display_name)
async def on_display_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не должно быть пустым. Введи ещё раз:")
        return
    await state.update_data(display_name=name)
    await state.set_state(OwnerOnboarding.default_lang)
    await message.answer("Язык по умолчанию (двухбуквенный код, например ru или en):")


@router.message(OwnerOnboarding.default_lang)
async def on_default_lang(message: Message, state: FSMContext) -> None:
    lang = (message.text or "").strip().lower()
    if len(lang) != 2 or not lang.isalpha():
        await message.answer("Нужен двухбуквенный код языка, например ru. Введи ещё раз:")
        return
    await state.update_data(default_lang=lang)
    data = await state.get_data()
    await state.set_state(OwnerOnboarding.confirm)
    await message.answer(
        f"Проверь данные:\nslug: {data['slug']}\nназвание: {data['display_name']}\nязык: {lang}\n\n"
        "Создаём бота?",
        reply_markup=confirm_kb(),
    )
```

Note: `cancel_kb` already exists in `quantuum/bot/ui/keyboards.py` (used by onboarding/profile). Reuse it.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_master_onboarding.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/master_onboarding.py tests/test_master_onboarding.py
git commit -m "feat(2b): master onboarding FSM — start + slug/name/lang collection"
```

---

### Task 11: Confirm/cancel handlers (create tenant + enqueue + await token)

**Files:**
- Modify: `src/quantuum/bot/handlers/master_onboarding.py`
- Test: `tests/test_master_onboarding.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_master_onboarding.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _FakeState:
    def __init__(self, data):
        self._data = dict(data)
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self._data = {}
        self.state = None


def _patch_sessionmaker(monkeypatch, module, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(module, "get_sessionmaker", lambda: _Maker())


async def test_confirm_creates_tenant_and_enqueues(session, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb
    from quantuum.db.models import Tenant
    from quantuum.domain.invites import create_invite

    _patch_sessionmaker(monkeypatch, mo, session)
    enqueued = {}

    async def fake_enqueue(tenant_id):
        enqueued["tenant_id"] = tenant_id

    monkeypatch.setattr(mo, "enqueue_provision_tenant", fake_enqueue)

    invite = await create_invite(session, created_by_account_id=None)
    state = _FakeState({"invite_id": invite.id, "slug": "acme", "display_name": "Acme", "default_lang": "ru"})
    query = AsyncMock()
    query.from_user = SimpleNamespace(id=555)
    query.message = SimpleNamespace(chat=SimpleNamespace(id=555), answer=AsyncMock())

    await mo.on_confirm(query, OwnerOnboardCb(action="confirm"), state, chat_id=555)

    from sqlmodel import select
    result = await session.execute(select(Tenant).where(Tenant.slug == "acme"))
    tenant = result.scalar_one()
    assert tenant.status == "provisioning"
    assert enqueued["tenant_id"] == tenant.id
    assert state.state == mo.ManualToken.awaiting
    assert (await state.get_data())["tenant_id"] == tenant.id


async def test_cancel_clears_state(monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    state = _FakeState({"slug": "x"})
    query = AsyncMock()
    query.message = SimpleNamespace(answer=AsyncMock())
    await mo.on_cancel(query, OwnerOnboardCb(action="cancel"), state)
    assert state.state is None
    assert await state.get_data() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_master_onboarding.py::test_confirm_creates_tenant_and_enqueues tests/test_master_onboarding.py::test_cancel_clears_state -v`
Expected: FAIL — `on_confirm` / `on_cancel` missing.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/master_onboarding.py`, add imports and handlers:

```python
from aiogram.types import CallbackQuery

from quantuum.domain.provisioning import create_tenant_from_onboarding
from quantuum.tasks.enqueue import enqueue_provision_tenant
```

```python
@router.callback_query(OwnerOnboardCb.filter(F.action == "confirm"), OwnerOnboarding.confirm)
async def on_confirm(
    query: CallbackQuery, callback_data: OwnerOnboardCb, state: FSMContext, chat_id: int | None = None
) -> None:
    data = await state.get_data()
    owner_tg_id = query.from_user.id
    owner_chat_id = chat_id if chat_id is not None else query.message.chat.id
    async with get_sessionmaker()() as session:
        invite = await get_invite_by_code_or_id(session, data["invite_id"])
        if invite is None or not invite_is_usable(invite):
            await query.message.answer("Приглашение больше недействительно.")
            await state.clear()
            await query.answer()
            return
        tenant = await create_tenant_from_onboarding(
            session,
            invite=invite,
            slug=data["slug"],
            display_name=data["display_name"],
            default_lang=data.get("default_lang", "ru"),
            owner_tg_id=owner_tg_id,
            owner_chat_id=owner_chat_id,
        )
    await enqueue_provision_tenant(tenant.id)
    await state.set_state(ManualToken.awaiting)
    await state.update_data(tenant_id=tenant.id)
    await query.message.answer("Создаю тенанта… Проверяю возможность автосоздания бота.")
    await query.answer()


@router.callback_query(OwnerOnboardCb.filter(F.action == "cancel"))
async def on_cancel(query: CallbackQuery, callback_data: OwnerOnboardCb, state: FSMContext) -> None:
    await state.clear()
    await query.message.answer("Онбординг отменён.")
    await query.answer()
```

Add the helper near `slug_is_available` (the FSM stores `invite_id`, so look up by primary key):

```python
async def get_invite_by_code_or_id(session, invite_id: int):
    from quantuum.db.models import TenantInvite

    return await session.get(TenantInvite, invite_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_master_onboarding.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/handlers/master_onboarding.py tests/test_master_onboarding.py
git commit -m "feat(2b): master onboarding confirm/cancel — create tenant + enqueue provision"
```

---

### Task 12: Manual-token handler → finalize provisioning

**Files:**
- Modify: `src/quantuum/bot/handlers/master_onboarding.py`
- Test: `tests/test_master_onboarding.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_master_onboarding.py`:

```python
async def test_manual_token_finalizes(session, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.db.models import Tenant
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)

    async def fake_validate(token):
        return (900, "zen_bot")

    monkeypatch.setattr(mo, "validate_bot_token", fake_validate)

    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="900:newtoken", answer=AsyncMock())

    await mo.on_manual_token(message, state)

    await session.refresh(tenant)
    assert tenant.status == "active"
    assert state.state is None  # cleared


async def test_manual_token_rejects_invalid(session, monkeypatch):
    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)

    async def fake_validate(token):
        return None

    monkeypatch.setattr(mo, "validate_bot_token", fake_validate)

    invite = await create_invite(session, created_by_account_id=None)
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="bad", display_name="Bad",
        default_lang="ru", owner_tg_id=1, owner_chat_id=1,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    message = SimpleNamespace(text="garbage", answer=AsyncMock())

    await mo.on_manual_token(message, state)

    await session.refresh(tenant)
    assert tenant.status != "active"  # still awaiting
    assert state.state is None or state.state == mo.ManualToken.awaiting
    message.answer.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_master_onboarding.py::test_manual_token_finalizes tests/test_master_onboarding.py::test_manual_token_rejects_invalid -v`
Expected: FAIL — `on_manual_token` missing.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/master_onboarding.py`, add import and handler:

```python
from quantuum.domain.provisioning import finalize_provisioning, validate_bot_token
```

```python
@router.message(ManualToken.awaiting)
async def on_manual_token(message: Message, state: FSMContext) -> None:
    token = (message.text or "").strip()
    result = await validate_bot_token(token)
    if result is None:
        await message.answer("Это не похоже на валидный токен бота. Пришли токен от @BotFather ещё раз:")
        return
    bot_id, username = result
    data = await state.get_data()
    async with get_sessionmaker()() as session:
        tenant_bot = await finalize_provisioning(
            session,
            tenant_id=data["tenant_id"],
            token=token,
            bot_telegram_id=bot_id,
            bot_username=username,
            default_lang=data.get("default_lang", "ru"),
        )
    await state.clear()
    await message.answer(
        f"Готово! Бот @{tenant_bot.bot_username} активирован. "
        "Он станет доступен после перезапуска воркера."
    )
```

Note the `validate_bot_token` and `finalize_provisioning` references are module-level names so the tests' `monkeypatch.setattr(mo, "validate_bot_token", ...)` works.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_master_onboarding.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/handlers/master_onboarding.py tests/test_master_onboarding.py
git commit -m "feat(2b): master bot manual-token handler → finalize provisioning"
```

---

### Task 13: Master dispatcher

**Files:**
- Create: `src/quantuum/bot/master_app.py`
- Test: `tests/test_master_app.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_master_app.py`:

```python
def test_create_master_dispatcher_has_onboarding_router():
    from quantuum.bot.master_app import create_master_dispatcher

    dp = create_master_dispatcher()
    # The onboarding router must be attached; astrology routers must not be.
    observers = dp.message.handlers
    assert observers  # has message handlers
    # Sanity: dispatcher builds without error and has a callback_query observer too
    assert dp.callback_query is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_master_app.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/quantuum/bot/master_app.py`:

```python
from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from quantuum.bot.middleware.account import AccountMiddleware
from quantuum.bot.middleware.tenant import TenantMiddleware
from quantuum.settings import get_settings


def create_master_dispatcher() -> Dispatcher:
    """Dispatcher for the platform master/onboarding bot — onboarding handlers only."""
    dp = Dispatcher(storage=RedisStorage.from_url(get_settings().redis_url))
    dp.message.middleware(TenantMiddleware())
    dp.message.middleware(AccountMiddleware())
    dp.callback_query.middleware(TenantMiddleware())
    dp.callback_query.middleware(AccountMiddleware())
    from quantuum.bot.handlers import master_onboarding

    dp.include_router(master_onboarding.router)
    return dp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_master_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/master_app.py tests/test_master_app.py
git commit -m "feat(2b): master dispatcher with onboarding handlers"
```

---

## Phase F — Process wiring

### Task 14: Polling — split master vs customer bots

**Files:**
- Modify: `src/quantuum/bot/polling.py`
- Test: `tests/test_bot_polling.py` (append)

- [ ] **Step 1: Read current `tests/test_bot_polling.py`**

Read it first to preserve existing assertions; add a split helper test.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_bot_polling.py`:

```python
async def test_split_polling_rows_by_platform(session, monkeypatch):
    from quantuum.bot.polling import split_by_platform
    from quantuum.db.models import Tenant, TenantBot

    platform = Tenant(slug="platform", display_name="P", is_platform=True)
    customer = Tenant(slug="cust", display_name="C")
    session.add(platform)
    session.add(customer)
    await session.flush()
    master = TenantBot(tenant_id=platform.id, bot_telegram_id=1, bot_token_enc=b"e", webhook_secret_path="m1")
    cust = TenantBot(tenant_id=customer.id, bot_telegram_id=2, bot_token_enc=b"e", webhook_secret_path="c1")
    session.add(master)
    session.add(cust)
    await session.commit()

    master_rows, customer_rows = await split_by_platform(session, [master, cust])
    assert [r.bot_telegram_id for r in master_rows] == [1]
    assert [r.bot_telegram_id for r in customer_rows] == [2]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_polling.py::test_split_polling_rows_by_platform -v`
Expected: FAIL — `split_by_platform` missing.

- [ ] **Step 4: Implement**

Rewrite `src/quantuum/bot/polling.py`:

```python
"""Local/dev long-polling entrypoint: customer bots + master bot on separate dispatchers."""

import asyncio

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.db.bootstrap import (
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_master_bot,
    ensure_platform_tenant,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_platform_tenant_id, list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger

logger = get_logger("bot.polling")


async def split_by_platform(session, rows):
    """Split tenant_bots rows into (master_rows, customer_rows) by tenant.is_platform."""
    platform_id = await get_platform_tenant_id(session)
    master_rows = [r for r in rows if r.tenant_id == platform_id]
    customer_rows = [r for r in rows if r.tenant_id != platform_id]
    return master_rows, customer_rows


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        rows = await list_active_tenant_bots(session, transport="polling")
        master_rows, customer_rows = await split_by_platform(session, rows)

    customer_pool = build_bots(customer_rows)
    master_pool = build_bots(master_rows)
    customer_dp = create_dispatcher()
    master_dp = create_master_dispatcher()

    for bot in list(customer_pool.values()) + list(master_pool.values()):
        await bot.delete_webhook(drop_pending_updates=True)

    logger.info("bot_polling_started", customer_bots=len(customer_pool), master_bots=len(master_pool))

    tasks = []
    if customer_pool:
        tasks.append(customer_dp.start_polling(*customer_pool.values(), handle_signals=False))
    if master_pool:
        tasks.append(master_dp.start_polling(*master_pool.values(), handle_signals=False))
    if not tasks:
        logger.warning("no_polling_bots_configured")
        return
    await asyncio.gather(*tasks)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_polling.py -v`
Expected: PASS (existing tests + new split test).

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/polling.py tests/test_bot_polling.py
git commit -m "feat(2b): polling splits master vs customer bots onto separate dispatchers"
```

---

### Task 15: Webhook runner — route master vs customer dispatchers

**Files:**
- Modify: `src/quantuum/bot/runner.py`
- Test: `tests/test_bot_runner.py` (rewrite)

- [ ] **Step 1: Write the failing test**

Rewrite `tests/test_bot_runner.py`:

```python
from unittest.mock import AsyncMock

from quantuum.bot.runner import WebhookConsumer


def _consumer(customer_pool, master_pool):
    return WebhookConsumer(
        customer_dp=AsyncMock(),
        master_dp=AsyncMock(),
        customer_pool=customer_pool,
        master_pool=master_pool,
    )


async def test_routes_customer_bot_to_customer_dp():
    bot = AsyncMock()
    c = _consumer({42: bot}, {})
    await c.process({"bot_id": 42, "update": {"update_id": 1}})
    c.customer_dp.feed_raw_update.assert_awaited_once()
    c.master_dp.feed_raw_update.assert_not_awaited()
    _, kwargs = c.customer_dp.feed_raw_update.await_args
    assert kwargs["bot"] is bot


async def test_routes_master_bot_to_master_dp():
    bot = AsyncMock()
    c = _consumer({}, {7: bot})
    await c.process({"bot_id": 7, "update": {"update_id": 1}})
    c.master_dp.feed_raw_update.assert_awaited_once()
    c.customer_dp.feed_raw_update.assert_not_awaited()


async def test_skips_unknown_bot():
    c = _consumer({}, {})
    await c.process({"bot_id": 99, "update": {"update_id": 1}})
    c.customer_dp.feed_raw_update.assert_not_awaited()
    c.master_dp.feed_raw_update.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_runner.py -v`
Expected: FAIL — `WebhookConsumer` missing.

- [ ] **Step 3: Implement**

Rewrite `src/quantuum/bot/runner.py`:

```python
import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.db.bootstrap import (
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_master_bot,
    ensure_platform_tenant,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_platform_tenant_id, list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update

logger = get_logger("bot.runner")


class WebhookConsumer:
    def __init__(
        self,
        *,
        customer_dp: Dispatcher,
        master_dp: Dispatcher,
        customer_pool: dict[int, Bot],
        master_pool: dict[int, Bot],
    ) -> None:
        self.customer_dp = customer_dp
        self.master_dp = master_dp
        self.customer_pool = customer_pool
        self.master_pool = master_pool

    async def process(self, envelope: dict) -> None:
        bot_id = envelope["bot_id"]
        if bot_id in self.master_pool:
            await self.master_dp.feed_raw_update(bot=self.master_pool[bot_id], update=envelope["update"])
            return
        bot = self.customer_pool.get(bot_id)
        if bot is None:
            logger.warning("update_for_unknown_bot", bot_id=bot_id)
            return
        await self.customer_dp.feed_raw_update(bot=bot, update=envelope["update"])


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        rows = await list_active_tenant_bots(session, transport="webhook")
        platform_id = await get_platform_tenant_id(session)

    master_rows = [r for r in rows if r.tenant_id == platform_id]
    customer_rows = [r for r in rows if r.tenant_id != platform_id]
    consumer = WebhookConsumer(
        customer_dp=create_dispatcher(),
        master_dp=create_master_dispatcher(),
        customer_pool=build_bots(customer_rows),
        master_pool=build_bots(master_rows),
    )
    logger.info(
        "bot_runner_started",
        customer_bots=len(consumer.customer_pool),
        master_bots=len(consumer.master_pool),
    )
    while True:
        envelope = await pop_update(timeout=5)
        if envelope is None:
            continue
        try:
            await consumer.process(envelope)
        except Exception:
            logger.exception("update_processing_failed", bot_id=envelope.get("bot_id"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/runner.py tests/test_bot_runner.py
git commit -m "feat(2b): webhook runner routes master vs customer bots to their dispatchers"
```

---

## Phase G — Deployment config

### Task 16: Compose env + .env.example + flow doc

**Files:**
- Modify: `docker-compose.yml`, `.env.example` (create if absent)
- Test: none (config) — verify by running the suite once more.

- [ ] **Step 1: Inspect existing compose/env**

Read `docker-compose.yml` and `.env.example` (or `.env`) to match the existing service env style.

- [ ] **Step 2: Add env vars to bot-worker, task-worker, api services**

Add (referencing host env, not hard-coded secrets) to each relevant service's `environment:`:

```yaml
      MASTER_BOT_TOKEN: ${MASTER_BOT_TOKEN:-}
      MASTER_BOT_USERNAME: ${MASTER_BOT_USERNAME:-}
      BOOTSTRAP_SUPERADMIN_EMAIL: ${BOOTSTRAP_SUPERADMIN_EMAIL:-}
```

`MASTER_BOT_TOKEN` + `MASTER_BOT_USERNAME` are needed by `bot-worker` (polling/runner) and `task-worker` (sends the manual-token prompt). `BOOTSTRAP_SUPERADMIN_EMAIL` is needed by `api` (lifespan bootstrap).

- [ ] **Step 3: Document new env in `.env.example`**

Append:

```dotenv
# Master / onboarding bot (separate from the product bot)
MASTER_BOT_TOKEN=
MASTER_BOT_USERNAME=
# First superadmin (created on api startup if the email has no identity yet)
BOOTSTRAP_SUPERADMIN_EMAIL=
```

- [ ] **Step 4: Add a short onboarding-flow note to the design plan folder**

Append a "## 2b runtime flow" section to this plan file documenting the end-to-end path (superadmin issues invite → owner deeplink → FSM → confirm → provision task → paste token → finalize → restart worker). Keep it to ~10 lines.

- [ ] **Step 5: Final full verification + commit**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass, ruff clean.

```bash
git add docker-compose.yml .env.example docs/superpowers/plans/2026-05-20-multitenancy-2b-onboarding.md
git commit -m "chore(2b): compose/.env master bot + superadmin env, flow docs"
```

---

## Self-Review (run before execution)

**Spec coverage (§4, §5, §8):**
- `tenant_invites` table ✓ (Task 1) — incl. presets, max_uses, status.
- `accounts.is_superadmin` + nullable `tenant_id` ✓ (Task 1).
- Platform tenant `is_platform=true, slug='platform'` ✓ (Task 3).
- Master bot owned by platform tenant, from `MASTER_BOT_TOKEN` ✓ (Task 3).
- Superadmin bootstrap from env ✓ (Task 3); magic-link superadmin login + `sa` JWT claim ✓ (Task 4); `require_superadmin` ✓ (Task 4).
- `POST/GET /admin/platform/invites`, revoke, `GET /admin/platform/tenants` ✓ (Task 6) with deeplink.
- Invite-onboarding FSM (deeplink → collect → confirm) ✓ (Tasks 10–11); fallback `awaiting_manual_token` FSM ✓ (Task 12).
- `provision_tenant` task with BotFather fallback ✓ (Task 9); `finalize_provisioning` (get_me, save token, owner account, grant owner role, status active) ✓ (Task 8).
- Multi-bot polling + webhook with separate master dispatcher ✓ (Tasks 13–15).

**Deliberate deviations from §8 (all spec-sanctioned):**
- FSM omits `telegram_username`/`description` collection — with fallback-only provisioning the bot username is read from `get_me()` after token paste; collecting/validating a desired username up front only mattered for programmatic creation (Open question #1).
- `seed_tenant_defaults` is a no-op seam — `tenant_languages`/`tenant_config` tables are Plan 5 (i18n).
- Self-service owner commands deferred to Plan 5 (user decision).
- Newly-provisioned bots go live on bot-worker restart (documented limitation).

**Placeholder scan:** none — every code step is complete. Migration uses a concrete handwritten revision id.

**Type/name consistency:** `issue_access_token(account_id, tenant_id, is_superadmin=False)` used consistently (Tasks 4, 6 tests). `validate_bot_token`/`finalize_provisioning`/`create_tenant_from_onboarding` signatures match across domain, task, and handlers. `WebhookConsumer.process` and `split_by_platform` referenced consistently in tests.

## 2b runtime flow

1. Superadmin calls `POST /admin/platform/invites` → receives a `t.me/masterbot?start=<code>` deeplink.
2. Prospective tenant owner opens the deeplink → master bot receives `/start <code>` → FSM validates invite and enters `collecting_info`.
3. FSM prompts for slug, display name, and language; owner replies → state advances through `collecting_slug` → `collecting_name` → `collecting_lang`.
4. Owner sends `/confirm` → handler calls `create_tenant_from_onboarding`, which creates a provisioning-status tenant and enqueues the `provision_tenant` arq task.
5. `provision_tenant` task attempts the BotFather API; on failure (or always in fallback mode) it sets tenant status to `awaiting_manual_token` and the master bot sends the owner a prompt to paste a BotFather token.
6. Owner pastes the token → `awaiting_manual_token` FSM handler calls `validate_bot_token` (Telegram `getMe`) to verify the token, then `finalize_provisioning`: encrypts and stores the token, creates the owner `Account` + `TenantRole`, and sets tenant status to `active`.
7. Bot goes live on the next bot-worker restart: `runner.py` queries all active `tenant_bots` rows and starts a polling loop (or registers a webhook) for each, including the newly activated bot.
