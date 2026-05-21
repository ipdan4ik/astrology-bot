# Payments 3a — Billing foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the billing data model and pure domain layer — plan catalog, balance crediting, quota↔package integration, plus read-only customer API and superadmin plan management — with no bot/Stars code (that is Plan 3b).

**Architecture:** Adds billing tables (`subscription_plans`, `package_plans`, `payment_providers`, `payments`, `account_subscriptions`, `account_packages`) on top of the existing `account_balance` quota engine (Plan 1). Crediting functions translate a paid `payment` into an `account_subscription` (extends `account_balance.subscription_active_until`) or an `account_package` (a FIFO-expiring credit ledger; `account_balance.package_credits` mirrors `SUM(requests_remaining)`). `consume_quota`/`refund_quota` are extended to keep the package ledger and the fast-path balance in lockstep. Global plans are seeded in bootstrap; customers read plans/balance/subscriptions/payments via `/v1/me/...`; superadmins manage plans via `/admin/platform/plans`.

**Tech Stack:** Python 3.12, FastAPI, SQLModel async, asyncpg, Alembic, Postgres (JSONB, partial unique index), pytest+httpx, uv.

**Scope notes:**
- **No bot, no Telegram Stars, no purchasing flow in 3a** — those are Plan 3b. 3a's crediting functions are exercised in tests by creating `payments` rows directly.
- API `POST /v1/me/subscriptions|packages` (purchase) is **Plan 3b** (it needs the provider abstraction). 3a ships only the read endpoints.
- `payouts` and `tenant_licenses` tables are **Plan 3b/later** (not used here).
- **Deliberate spec deviations** (documented): subscription `period` stored as `period_days: int` and package expiry as `expires_after_days: int | None` instead of Postgres `interval`/text — keeps `ends_at` arithmetic trivial and fully unit-testable without new deps (calendar-accurate months deferred). For currency `XTR` (Telegram Stars), `price_cents` holds the **integer Star amount** (XTR has no decimal subunit).

---

## File Structure

**New files:**
- `src/quantuum/domain/plans.py` — plan catalog queries.
- `src/quantuum/domain/billing.py` — payments recording + crediting (`apply_*_payment`, `recompute_account_balance`).
- `src/quantuum/api/routes/billing.py` — superadmin plan CRUD (`/admin/platform/plans`).
- Test files mirroring each.

**Modified files:**
- `src/quantuum/db/models.py` — 6 billing models.
- `alembic/versions/<two new>.py` — migrations.
- `src/quantuum/db/bootstrap.py` — `ensure_global_plans`.
- `src/quantuum/api/app.py` — wire bootstrap + billing router.
- `src/quantuum/api/schemas.py` — plan/balance/subscription/payment schemas.
- `src/quantuum/api/routes/me.py` — read endpoints (balance, plans, subscriptions, payments).
- `src/quantuum/domain/quota.py` — package-ledger integration in consume/refund.

---

## Phase A — Data model

### Task 1: Plan catalog models (subscription_plans, package_plans) + migration

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/b1a2c3d4e5f6_plan_catalog.py`
- Test: `tests/test_billing_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_billing_models.py`:

```python
from quantuum.db.models import PackagePlan, SubscriptionPlan


async def test_subscription_plan_defaults(session):
    p = SubscriptionPlan(slug="monthly", name="Monthly", period_days=30, price_cents=250)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.currency == "XTR"
    assert p.active is True
    assert p.tenant_id is None  # global by default


async def test_package_plan_defaults(session):
    p = PackagePlan(slug="pack_small", name="Small", request_count=5, price_cents=400)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.expires_after_days is None
    assert p.currency == "XTR"
    assert p.active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_models.py -v`
Expected: FAIL — `ImportError` (no `SubscriptionPlan`/`PackagePlan`).

- [ ] **Step 3: Implement models**

In `src/quantuum/db/models.py`, append (after `AccountBalance`):

```python
class SubscriptionPlan(SQLModel, table=True):
    __tablename__ = "subscription_plans"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    slug: str = Field(index=True)
    name: str
    period_days: int  # MVP: integer days instead of calendar interval
    price_cents: int  # for XTR this is the integer Star amount
    currency: str = "XTR"
    active: bool = True
    created_at: datetime = _dt_field(default_factory=utcnow)


class PackagePlan(SQLModel, table=True):
    __tablename__ = "package_plans"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    slug: str = Field(index=True)
    name: str
    request_count: int
    price_cents: int  # for XTR this is the integer Star amount
    currency: str = "XTR"
    expires_after_days: int | None = None  # NULL = never expires
    active: bool = True
    created_at: datetime = _dt_field(default_factory=utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing_models.py -v`
Expected: PASS.

- [ ] **Step 5: Write the migration**

Create `alembic/versions/b1a2c3d4e5f6_plan_catalog.py`:

```python
"""plan catalog: subscription_plans, package_plans

Revision ID: b1a2c3d4e5f6
Revises: a2b1c0d9e8f7
Create Date: 2026-05-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "a2b1c0d9e8f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscription_plans_slug"), "subscription_plans", ["slug"], unique=False)
    op.create_index(op.f("ix_subscription_plans_tenant_id"), "subscription_plans", ["tenant_id"], unique=False)
    op.create_table(
        "package_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_after_days", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_package_plans_slug"), "package_plans", ["slug"], unique=False)
    op.create_index(op.f("ix_package_plans_tenant_id"), "package_plans", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_package_plans_tenant_id"), table_name="package_plans")
    op.drop_index(op.f("ix_package_plans_slug"), table_name="package_plans")
    op.drop_table("package_plans")
    op.drop_index(op.f("ix_subscription_plans_tenant_id"), table_name="subscription_plans")
    op.drop_index(op.f("ix_subscription_plans_slug"), table_name="subscription_plans")
    op.drop_table("subscription_plans")
```

- [ ] **Step 6: Verify migration applies + no drift**

Run: `uv run alembic upgrade head` (targets the app DB at 172.29.0.2; the test DB at 172.30.0.2 is managed by `create_all`).
Run: `uv run alembic check` → "No new upgrade operations detected." (If `alembic check` is unavailable, autogenerate a scratch revision, confirm empty `upgrade()`, then delete it.)

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/db/models.py alembic/versions/b1a2c3d4e5f6_plan_catalog.py tests/test_billing_models.py
git commit -m "feat(3a): subscription_plans + package_plans models + migration"
```

---

### Task 2: Payments + account billing models + migration

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/c2b3d4e5f6a7_payments_and_account_billing.py`
- Test: `tests/test_billing_models.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_billing_models.py`:

```python
async def test_payment_and_account_billing_rows(session, default_tenant):
    from quantuum.db.models import (
        Account,
        AccountPackage,
        AccountSubscription,
        PackagePlan,
        Payment,
        PaymentProvider,
        SubscriptionPlan,
    )
    from quantuum.common.datetime import utcnow

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()

    provider = PaymentProvider(tenant_id=default_tenant.id, kind="tg_stars", config_enc=b"")
    session.add(provider)
    await session.flush()

    pay = Payment(
        tenant_id=default_tenant.id, account_id=acc.id, provider_id=provider.id,
        amount_cents=250, currency="XTR", status="pending", metadata_json={"plan": "monthly"},
    )
    session.add(pay)
    await session.flush()
    assert pay.id is not None
    assert pay.metadata_json == {"plan": "monthly"}

    sub_plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    pkg_plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=400)
    session.add(sub_plan)
    session.add(pkg_plan)
    await session.flush()

    sub = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=sub_plan.id,
        status="active", started_at=utcnow(), ends_at=utcnow(),
    )
    pkg = AccountPackage(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=pkg_plan.id,
        requests_remaining=5, payment_id=pay.id,
    )
    session.add(sub)
    session.add(pkg)
    await session.commit()
    assert sub.id is not None and pkg.id is not None


async def test_active_subscription_partial_unique(session, default_tenant):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from quantuum.common.datetime import utcnow
    from quantuum.db.models import Account, AccountSubscription, SubscriptionPlan

    acc = Account(tenant_id=default_tenant.id)
    plan = SubscriptionPlan(slug="m2", name="M2", period_days=30, price_cents=1)
    session.add(acc)
    session.add(plan)
    await session.flush()

    common = dict(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                  started_at=utcnow(), ends_at=utcnow())
    session.add(AccountSubscription(status="active", **common))
    await session.commit()
    session.add(AccountSubscription(status="grace", **common))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_models.py::test_payment_and_account_billing_rows -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement models**

In `src/quantuum/db/models.py`, widen the SQLAlchemy import line to add `Index` and `text`, and add the JSONB import:

```python
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
```

Append the models:

```python
class PaymentProvider(SQLModel, table=True):
    __tablename__ = "payment_providers"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    kind: str  # tg_stars|cloudpayments|cryptobot
    config_enc: bytes = b""
    active: bool = True
    created_at: datetime = _dt_field(default_factory=utcnow)


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    provider_id: int | None = Field(default=None, foreign_key="payment_providers.id")
    amount_cents: int
    currency: str = "XTR"
    external_id: str | None = Field(default=None, index=True)
    status: str = "pending"  # pending|paid|refunded|failed
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}"))
    created_at: datetime = _dt_field(default_factory=utcnow)
    paid_at: datetime | None = _dt_field(default=None)
    refunded_at: datetime | None = _dt_field(default=None)


class AccountSubscription(SQLModel, table=True):
    __tablename__ = "account_subscriptions"
    __table_args__ = (
        Index(
            "uq_active_subscription_per_plan",
            "account_id",
            "plan_id",
            unique=True,
            postgresql_where=text("status IN ('active','grace')"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    plan_id: int = Field(foreign_key="subscription_plans.id")
    status: str = "active"  # active|grace|expired|cancelled
    started_at: datetime = _dt_field(default_factory=utcnow)
    ends_at: datetime = _dt_field(default_factory=utcnow)
    renewed_at: datetime | None = _dt_field(default=None)
    cancelled_at: datetime | None = _dt_field(default=None)
    payment_id: int | None = Field(default=None, foreign_key="payments.id")
    created_at: datetime = _dt_field(default_factory=utcnow)


class AccountPackage(SQLModel, table=True):
    __tablename__ = "account_packages"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    plan_id: int = Field(foreign_key="package_plans.id")
    requests_remaining: int
    purchased_at: datetime = _dt_field(default_factory=utcnow)
    expires_at: datetime | None = _dt_field(default=None)
    payment_id: int | None = Field(default=None, foreign_key="payments.id")
    created_at: datetime = _dt_field(default_factory=utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing_models.py -v`
Expected: PASS (including the partial-unique IntegrityError test).

- [ ] **Step 5: Write the migration**

Create `alembic/versions/c2b3d4e5f6a7_payments_and_account_billing.py`:

```python
"""payments + account billing: payment_providers, payments, account_subscriptions, account_packages

Revision ID: c2b3d4e5f6a7
Revises: b1a2c3d4e5f6
Create Date: 2026-05-21 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = "c2b3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("config_enc", sa.LargeBinary(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_providers_tenant_id"), "payment_providers", ["tenant_id"], unique=False)
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["payment_providers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_account_id"), "payments", ["account_id"], unique=False)
    op.create_index(op.f("ix_payments_external_id"), "payments", ["external_id"], unique=False)
    op.create_index(op.f("ix_payments_tenant_id"), "payments", ["tenant_id"], unique=False)
    op.create_table(
        "account_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_subscriptions_account_id"), "account_subscriptions", ["account_id"], unique=False)
    op.create_index(op.f("ix_account_subscriptions_tenant_id"), "account_subscriptions", ["tenant_id"], unique=False)
    op.create_index(
        "uq_active_subscription_per_plan",
        "account_subscriptions",
        ["account_id", "plan_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active','grace')"),
    )
    op.create_table(
        "account_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("requests_remaining", sa.Integer(), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["package_plans.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_packages_account_id"), "account_packages", ["account_id"], unique=False)
    op.create_index(op.f("ix_account_packages_tenant_id"), "account_packages", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_account_packages_tenant_id"), table_name="account_packages")
    op.drop_index(op.f("ix_account_packages_account_id"), table_name="account_packages")
    op.drop_table("account_packages")
    op.drop_index("uq_active_subscription_per_plan", table_name="account_subscriptions")
    op.drop_index(op.f("ix_account_subscriptions_tenant_id"), table_name="account_subscriptions")
    op.drop_index(op.f("ix_account_subscriptions_account_id"), table_name="account_subscriptions")
    op.drop_table("account_subscriptions")
    op.drop_index(op.f("ix_payments_tenant_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_external_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_account_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_payment_providers_tenant_id"), table_name="payment_providers")
    op.drop_table("payment_providers")
```

- [ ] **Step 6: Verify migration + no drift**

Run: `uv run alembic upgrade head` then `uv run alembic check` (or autogenerate-and-confirm-empty). Expected: clean, no drift. (Note: the partial-unique index `uq_active_subscription_per_plan` is defined in the model `__table_args__`, so autogenerate must NOT want to add/drop it.)

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/db/models.py alembic/versions/c2b3d4e5f6a7_payments_and_account_billing.py tests/test_billing_models.py
git commit -m "feat(3a): payments + account_subscriptions/packages + payment_providers models + migration"
```

---

## Phase B — Domain

### Task 3: Plan catalog domain + global plan seeding

**Files:**
- Create: `src/quantuum/domain/plans.py`
- Modify: `src/quantuum/db/bootstrap.py`, `src/quantuum/api/app.py`
- Test: `tests/test_plans_domain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plans_domain.py`:

```python
from quantuum.db.bootstrap import ensure_global_plans
from quantuum.domain.plans import (
    get_package_plan,
    get_subscription_plan,
    list_package_plans,
    list_subscription_plans,
)


async def test_ensure_global_plans_idempotent(session):
    await ensure_global_plans(session)
    await ensure_global_plans(session)  # idempotent

    subs = await list_subscription_plans(session, tenant_id=None)
    pkgs = await list_package_plans(session, tenant_id=None)
    assert {s.slug for s in subs} == {"monthly"}
    assert {p.slug for p in pkgs} == {"pack_small", "pack_large"}


async def test_list_plans_unions_global_and_tenant(session, default_tenant):
    from quantuum.db.models import SubscriptionPlan

    await ensure_global_plans(session)
    session.add(
        SubscriptionPlan(tenant_id=default_tenant.id, slug="custom", name="Custom",
                         period_days=7, price_cents=99)
    )
    await session.commit()

    subs = await list_subscription_plans(session, tenant_id=default_tenant.id)
    slugs = {s.slug for s in subs}
    assert "monthly" in slugs  # global
    assert "custom" in slugs  # tenant-specific


async def test_get_plan_only_active(session):
    from quantuum.db.models import SubscriptionPlan

    p = SubscriptionPlan(slug="dead", name="Dead", period_days=30, price_cents=1, active=False)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert await get_subscription_plan(session, p.id) is None  # inactive not returned


async def test_get_package_plan(session):
    from quantuum.db.models import PackagePlan

    p = PackagePlan(slug="x", name="X", request_count=3, price_cents=10)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    got = await get_package_plan(session, p.id)
    assert got is not None and got.request_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plans_domain.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement plan domain**

Create `src/quantuum/domain/plans.py`:

```python
from sqlmodel import or_, select

from quantuum.db.models import PackagePlan, SubscriptionPlan


async def list_subscription_plans(session, *, tenant_id: int | None) -> list[SubscriptionPlan]:
    query = select(SubscriptionPlan).where(SubscriptionPlan.active == True)  # noqa: E712
    if tenant_id is None:
        query = query.where(SubscriptionPlan.tenant_id.is_(None))
    else:
        query = query.where(
            or_(SubscriptionPlan.tenant_id.is_(None), SubscriptionPlan.tenant_id == tenant_id)
        )
    result = await session.execute(query.order_by(SubscriptionPlan.id))
    return list(result.scalars().all())


async def list_package_plans(session, *, tenant_id: int | None) -> list[PackagePlan]:
    query = select(PackagePlan).where(PackagePlan.active == True)  # noqa: E712
    if tenant_id is None:
        query = query.where(PackagePlan.tenant_id.is_(None))
    else:
        query = query.where(
            or_(PackagePlan.tenant_id.is_(None), PackagePlan.tenant_id == tenant_id)
        )
    result = await session.execute(query.order_by(PackagePlan.id))
    return list(result.scalars().all())


async def get_subscription_plan(session, plan_id: int) -> SubscriptionPlan | None:
    plan = await session.get(SubscriptionPlan, plan_id)
    return plan if plan is not None and plan.active else None


async def get_package_plan(session, plan_id: int) -> PackagePlan | None:
    plan = await session.get(PackagePlan, plan_id)
    return plan if plan is not None and plan.active else None
```

- [ ] **Step 4: Implement seeding**

In `src/quantuum/db/bootstrap.py`, widen the models import to add `PackagePlan, SubscriptionPlan` and append:

```python
async def ensure_global_plans(session) -> None:
    """Seed global (tenant_id NULL) plan structure with placeholder prices (idempotent).

    Prices are placeholders in XTR (Star amount) — adjust later via /admin/platform/plans.
    """
    sub_exists = await session.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.tenant_id.is_(None), SubscriptionPlan.slug == "monthly"
        )
    )
    if sub_exists.scalar_one_or_none() is None:
        session.add(
            SubscriptionPlan(slug="monthly", name="Monthly", period_days=30, price_cents=250)
        )
    for slug, name, count, price in (
        ("pack_small", "Small pack", 5, 400),
        ("pack_large", "Large pack", 20, 1200),
    ):
        pkg_exists = await session.execute(
            select(PackagePlan).where(PackagePlan.tenant_id.is_(None), PackagePlan.slug == slug)
        )
        if pkg_exists.scalar_one_or_none() is None:
            session.add(PackagePlan(slug=slug, name=name, request_count=count, price_cents=price))
    await session.commit()
```

- [ ] **Step 5: Wire seeding into the API lifespan**

In `src/quantuum/api/app.py`, add `ensure_global_plans` to the bootstrap import and call it in `_lifespan` (after `ensure_superadmin`):

```python
        await ensure_global_plans(session)
```

- [ ] **Step 6: Run tests + suite + commit**

Run: `uv run pytest tests/test_plans_domain.py -v && uv run pytest -q && uv run ruff check .`
Expected: PASS.

```bash
git add src/quantuum/domain/plans.py src/quantuum/db/bootstrap.py src/quantuum/api/app.py tests/test_plans_domain.py
git commit -m "feat(3a): plan catalog domain + global plan seeding"
```

---

### Task 4: Payments domain (record + mark paid, idempotent)

**Files:**
- Create: `src/quantuum/domain/billing.py`
- Test: `tests/test_billing_payments.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_billing_payments.py`:

```python
from quantuum.db.models import Account
from quantuum.domain.billing import (
    get_payment_by_external_id,
    mark_payment_paid,
    record_pending_payment,
)


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    return acc


async def test_record_pending_payment(session, default_tenant):
    acc = await _account(session, default_tenant)
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR", metadata={"kind": "subscription", "plan_id": 1},
    )
    assert pay.id is not None
    assert pay.status == "pending"
    assert pay.metadata_json["plan_id"] == 1


async def test_mark_payment_paid_idempotent(session, default_tenant):
    acc = await _account(session, default_tenant)
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR", metadata={},
    )
    p1 = await mark_payment_paid(session, payment_id=pay.id, external_id="charge_123")
    assert p1.status == "paid"
    assert p1.external_id == "charge_123"
    assert p1.paid_at is not None
    first_paid_at = p1.paid_at

    # Idempotent: marking again does not change paid_at or duplicate
    p2 = await mark_payment_paid(session, payment_id=pay.id, external_id="charge_123")
    assert p2.paid_at == first_paid_at

    found = await get_payment_by_external_id(session, "charge_123")
    assert found is not None and found.id == pay.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_payments.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/quantuum/domain/billing.py`:

```python
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import Payment


async def record_pending_payment(
    session,
    *,
    tenant_id: int,
    account_id: int,
    provider_id: int | None,
    amount_cents: int,
    currency: str,
    metadata: dict,
) -> Payment:
    payment = Payment(
        tenant_id=tenant_id,
        account_id=account_id,
        provider_id=provider_id,
        amount_cents=amount_cents,
        currency=currency,
        status="pending",
        metadata_json=metadata,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def get_payment_by_external_id(session, external_id: str) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.external_id == external_id))
    return result.scalar_one_or_none()


async def mark_payment_paid(session, *, payment_id: int, external_id: str) -> Payment:
    """Mark a payment paid (idempotent: re-marking a paid payment is a no-op)."""
    payment = await session.get(Payment, payment_id)
    if payment.status == "paid":
        return payment
    payment.status = "paid"
    payment.external_id = external_id
    payment.paid_at = utcnow()
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing_payments.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/billing.py tests/test_billing_payments.py
git commit -m "feat(3a): payments domain — record_pending_payment + idempotent mark_payment_paid"
```

---

### Task 5: Balance crediting (recompute + apply subscription/package)

**Files:**
- Modify: `src/quantuum/domain/billing.py`
- Test: `tests/test_billing_crediting.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_billing_crediting.py`:

```python
from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountPackage,
    PackagePlan,
    SubscriptionPlan,
)
from quantuum.domain.billing import (
    apply_package_payment,
    apply_subscription_payment,
    recompute_account_balance,
)


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    return acc


async def test_apply_subscription_payment_sets_balance(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()

    sub = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    assert sub.status == "active"
    bal = await session.get(AccountBalance, acc.id)
    assert bal.subscription_active_until is not None
    assert bal.subscription_active_until > utcnow() + timedelta(days=29)


async def test_renewal_extends_existing_subscription(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()

    sub1 = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    first_end = sub1.ends_at
    sub2 = await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    assert sub2.id == sub1.id  # same row, extended (no duplicate active sub)
    assert sub2.ends_at > first_end
    assert sub2.renewed_at is not None


async def test_apply_package_payment_credits(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=400)
    session.add(plan)
    await session.flush()

    await apply_package_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5

    await apply_package_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 10  # two packages summed


async def test_recompute_excludes_expired_packages(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=1)
    session.add(plan)
    await session.flush()
    session.add(AccountPackage(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        requests_remaining=5, expires_at=utcnow() - timedelta(days=1),
    ))
    session.add(AccountPackage(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        requests_remaining=3, expires_at=None,
    ))
    await session.commit()

    bal = await recompute_account_balance(session, acc.id)
    assert bal.package_credits == 3  # expired pack excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_crediting.py -v`
Expected: FAIL — functions missing.

- [ ] **Step 3: Implement**

In `src/quantuum/domain/billing.py`, add imports and functions:

```python
from datetime import timedelta

from sqlmodel import or_

from quantuum.db.models import (
    AccountBalance,
    AccountPackage,
    AccountSubscription,
    PackagePlan,
    SubscriptionPlan,
)
```

```python
async def _ensure_balance(session, account_id: int) -> AccountBalance:
    balance = await session.get(AccountBalance, account_id)
    if balance is None:
        balance = AccountBalance(account_id=account_id)
        session.add(balance)
        await session.flush()
    return balance


async def recompute_account_balance(session, account_id: int) -> AccountBalance:
    """Recompute package_credits (sum of valid package rows) and subscription_active_until
    (latest active/grace subscription end) from the ledger tables."""
    now = utcnow()
    balance = await _ensure_balance(session, account_id)

    pkg_result = await session.execute(
        select(AccountPackage.requests_remaining).where(
            AccountPackage.account_id == account_id,
            or_(AccountPackage.expires_at.is_(None), AccountPackage.expires_at > now),
        )
    )
    balance.package_credits = sum(pkg_result.scalars().all())

    sub_result = await session.execute(
        select(AccountSubscription.ends_at).where(
            AccountSubscription.account_id == account_id,
            AccountSubscription.status.in_(("active", "grace")),
        )
    )
    ends = list(sub_result.scalars().all())
    balance.subscription_active_until = max(ends) if ends else None

    balance.updated_at = now
    session.add(balance)
    await session.commit()
    await session.refresh(balance)
    return balance


async def apply_subscription_payment(
    session, *, account_id: int, tenant_id: int, plan: SubscriptionPlan, payment_id: int | None
) -> AccountSubscription:
    """Create or renew the account's subscription for this plan, then refresh the balance."""
    now = utcnow()
    result = await session.execute(
        select(AccountSubscription).where(
            AccountSubscription.account_id == account_id,
            AccountSubscription.plan_id == plan.id,
            AccountSubscription.status.in_(("active", "grace")),
        )
    )
    sub = result.scalar_one_or_none()
    if sub is not None:
        base = max(sub.ends_at, now)
        sub.ends_at = base + timedelta(days=plan.period_days)
        sub.renewed_at = now
        sub.status = "active"
    else:
        sub = AccountSubscription(
            tenant_id=tenant_id,
            account_id=account_id,
            plan_id=plan.id,
            status="active",
            started_at=now,
            ends_at=now + timedelta(days=plan.period_days),
            payment_id=payment_id,
        )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    await recompute_account_balance(session, account_id)
    return sub


async def apply_package_payment(
    session, *, account_id: int, tenant_id: int, plan: PackagePlan, payment_id: int | None
) -> AccountPackage:
    """Add a package credit ledger row, then refresh the balance."""
    now = utcnow()
    expires_at = (
        now + timedelta(days=plan.expires_after_days) if plan.expires_after_days else None
    )
    pkg = AccountPackage(
        tenant_id=tenant_id,
        account_id=account_id,
        plan_id=plan.id,
        requests_remaining=plan.request_count,
        purchased_at=now,
        expires_at=expires_at,
        payment_id=payment_id,
    )
    session.add(pkg)
    await session.commit()
    await session.refresh(pkg)
    await recompute_account_balance(session, account_id)
    return pkg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing_crediting.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/domain/billing.py tests/test_billing_crediting.py
git commit -m "feat(3a): balance crediting — recompute + apply subscription/package payment"
```

---

### Task 6: Quota ↔ package-ledger integration

**Files:**
- Modify: `src/quantuum/domain/quota.py`
- Test: `tests/test_quota.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_quota.py`:

```python
async def test_consume_decrements_oldest_package_row(session, default_tenant):
    from datetime import timedelta

    from quantuum.common.datetime import utcnow
    from quantuum.db.models import Account, AccountBalance, AccountPackage, PackagePlan
    from quantuum.domain.quota import consume_quota

    acc = Account(tenant_id=default_tenant.id)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=1)
    session.add(acc)
    session.add(plan)
    await session.flush()
    # mark trial used so consume falls through to packages
    session.add(AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=2))
    older = AccountPackage(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                           requests_remaining=1, expires_at=utcnow() + timedelta(days=1))
    newer = AccountPackage(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                           requests_remaining=1, expires_at=utcnow() + timedelta(days=30))
    session.add(older)
    session.add(newer)
    await session.commit()

    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "package"

    await session.refresh(older)
    await session.refresh(newer)
    assert older.requests_remaining == 0  # oldest-expiring decremented first
    assert newer.requests_remaining == 1
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 1


async def test_refund_package_restores_credit(session, default_tenant):
    from datetime import timedelta

    from quantuum.common.datetime import utcnow
    from quantuum.db.models import Account, AccountBalance, AccountPackage, PackagePlan, Request
    from quantuum.domain.quota import refund_quota

    acc = Account(tenant_id=default_tenant.id)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=1)
    session.add(acc)
    session.add(plan)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=0))
    session.add(AccountPackage(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                               requests_remaining=0, expires_at=utcnow() + timedelta(days=30)))
    req = Request(tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
                  status="failed", charged_against="package")
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_quota.py::test_consume_decrements_oldest_package_row tests/test_quota.py::test_refund_package_restores_credit -v`
Expected: FAIL — current `consume_quota` does not touch `account_packages` rows (older/newer unchanged).

- [ ] **Step 3: Implement**

Rewrite `src/quantuum/domain/quota.py` to keep the package ledger and the fast-path balance in lockstep:

```python
from sqlmodel import or_, select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, AccountPackage, Request


async def _oldest_valid_package(session, account_id: int) -> AccountPackage | None:
    now = utcnow()
    result = await session.execute(
        select(AccountPackage)
        .where(
            AccountPackage.account_id == account_id,
            AccountPackage.requests_remaining > 0,
            or_(AccountPackage.expires_at.is_(None), AccountPackage.expires_at > now),
        )
        .order_by(AccountPackage.expires_at.is_(None), AccountPackage.expires_at, AccountPackage.purchased_at)
    )
    return result.scalars().first()


async def _newest_valid_package(session, account_id: int) -> AccountPackage | None:
    now = utcnow()
    result = await session.execute(
        select(AccountPackage)
        .where(
            AccountPackage.account_id == account_id,
            or_(AccountPackage.expires_at.is_(None), AccountPackage.expires_at > now),
        )
        .order_by(AccountPackage.purchased_at.desc())
    )
    return result.scalars().first()


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
        await session.commit()
        return "subscription"

    if balance.package_credits >= 1:
        # Decrement the oldest-expiring package ledger row to mirror the credit spend.
        pkg = await _oldest_valid_package(session, account_id)
        if pkg is not None:
            pkg.requests_remaining -= 1
            session.add(pkg)
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
            pkg = await _newest_valid_package(session, request.account_id)
            if pkg is not None:
                pkg.requests_remaining += 1
                session.add(pkg)
        balance.updated_at = utcnow()
        session.add(balance)

    request.charged_against = "none"
    request.status = "refunded"
    session.add(request)
    await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_quota.py -v`
Expected: PASS (existing quota tests + new ledger tests).

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/domain/quota.py tests/test_quota.py
git commit -m "feat(3a): consume/refund_quota keep account_packages ledger in lockstep with balance"
```

---

## Phase C — Read API & plan management

### Task 7: Customer read endpoints — balance + plans

**Files:**
- Modify: `src/quantuum/api/schemas.py`, `src/quantuum/api/routes/me.py`
- Test: `tests/test_api_billing_me.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_billing_me.py`:

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.bootstrap import ensure_global_plans
from quantuum.db.models import Account, AccountBalance


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id, package_credits=3))
    await ensure_global_plans(session)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_get_balance(client, auth):
    r = await client.get("/v1/me/balance", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["package_credits"] == 3
    assert body["free_trial_used"] is False


async def test_get_plans(client, auth):
    r = await client.get("/v1/me/plans", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert {p["slug"] for p in body["subscriptions"]} == {"monthly"}
    assert {p["slug"] for p in body["packages"]} == {"pack_small", "pack_large"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_billing_me.py -v`
Expected: FAIL — 404 (routes missing).

- [ ] **Step 3: Add schemas**

In `src/quantuum/api/schemas.py`, append:

```python
class BalanceOut(BaseModel):
    free_trial_used: bool
    subscription_active_until: str | None
    package_credits: int


class SubscriptionPlanOut(BaseModel):
    id: int
    slug: str
    name: str
    period_days: int
    price_cents: int
    currency: str


class PackagePlanOut(BaseModel):
    id: int
    slug: str
    name: str
    request_count: int
    price_cents: int
    currency: str
    expires_after_days: int | None


class PlansOut(BaseModel):
    subscriptions: list[SubscriptionPlanOut]
    packages: list[PackagePlanOut]
```

- [ ] **Step 4: Implement routes**

In `src/quantuum/api/routes/me.py`, add imports:

```python
from quantuum.api.schemas import (
    BalanceOut,
    PackagePlanOut,
    PlansOut,
    SubscriptionPlanOut,
)
from quantuum.db.models import AccountBalance
from quantuum.domain.plans import list_package_plans, list_subscription_plans
```

(merge into the existing `from quantuum.api.schemas import ...` and `from quantuum.db.models import ...` lines).

Append routes:

```python
@router.get("/balance", response_model=BalanceOut)
async def get_balance(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BalanceOut:
    balance = await session.get(AccountBalance, account.id)
    if balance is None:
        return BalanceOut(free_trial_used=False, subscription_active_until=None, package_credits=0)
    return BalanceOut(
        free_trial_used=balance.free_trial_used,
        subscription_active_until=(
            balance.subscription_active_until.isoformat()
            if balance.subscription_active_until
            else None
        ),
        package_credits=balance.package_credits,
    )


@router.get("/plans", response_model=PlansOut)
async def get_plans(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> PlansOut:
    subs = await list_subscription_plans(session, tenant_id=account.tenant_id)
    pkgs = await list_package_plans(session, tenant_id=account.tenant_id)
    return PlansOut(
        subscriptions=[
            SubscriptionPlanOut(
                id=s.id, slug=s.slug, name=s.name, period_days=s.period_days,
                price_cents=s.price_cents, currency=s.currency,
            )
            for s in subs
        ],
        packages=[
            PackagePlanOut(
                id=p.id, slug=p.slug, name=p.name, request_count=p.request_count,
                price_cents=p.price_cents, currency=p.currency,
                expires_after_days=p.expires_after_days,
            )
            for p in pkgs
        ],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_billing_me.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/api/schemas.py src/quantuum/api/routes/me.py tests/test_api_billing_me.py
git commit -m "feat(3a): customer read API — GET /v1/me/balance + /v1/me/plans"
```

---

### Task 8: Customer read endpoints — subscriptions + payments

**Files:**
- Modify: `src/quantuum/api/schemas.py`, `src/quantuum/api/routes/me.py`
- Test: `tests/test_api_billing_me.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_billing_me.py`:

```python
async def test_get_subscriptions_and_payments(client, auth, session, default_tenant):
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import AccountSubscription, Payment, SubscriptionPlan

    # find the account id from the token-bound balance row created in the auth fixture
    from sqlmodel import select
    acc_id = (await session.execute(select(Account.id))).scalars().first()

    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc_id, plan_id=plan.id,
        status="active", started_at=utcnow(), ends_at=utcnow(),
    ))
    session.add(Payment(
        tenant_id=default_tenant.id, account_id=acc_id, amount_cents=250,
        currency="XTR", status="paid",
    ))
    await session.commit()

    rs = await client.get("/v1/me/subscriptions", headers=auth)
    assert rs.status_code == 200
    assert any(s["status"] == "active" for s in rs.json())

    rp = await client.get("/v1/me/payments", headers=auth)
    assert rp.status_code == 200
    assert any(p["amount_cents"] == 250 and p["status"] == "paid" for p in rp.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_billing_me.py::test_get_subscriptions_and_payments -v`
Expected: FAIL — 404.

- [ ] **Step 3: Add schemas**

In `src/quantuum/api/schemas.py`, append:

```python
class SubscriptionOut(BaseModel):
    id: int
    plan_id: int
    status: str
    started_at: str
    ends_at: str


class PaymentOut(BaseModel):
    id: int
    amount_cents: int
    currency: str
    status: str
    created_at: str
    paid_at: str | None
```

- [ ] **Step 4: Implement routes**

In `src/quantuum/api/routes/me.py`, add to the model import `AccountSubscription, Payment` and append:

```python
@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionOut]:
    result = await session.execute(
        select(AccountSubscription)
        .where(AccountSubscription.account_id == account.id)
        .order_by(AccountSubscription.id.desc())
    )
    return [
        SubscriptionOut(
            id=s.id, plan_id=s.plan_id, status=s.status,
            started_at=s.started_at.isoformat(), ends_at=s.ends_at.isoformat(),
        )
        for s in result.scalars().all()
    ]


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentOut]:
    result = await session.execute(
        select(Payment).where(Payment.account_id == account.id).order_by(Payment.id.desc())
    )
    return [
        PaymentOut(
            id=p.id, amount_cents=p.amount_cents, currency=p.currency, status=p.status,
            created_at=p.created_at.isoformat(),
            paid_at=p.paid_at.isoformat() if p.paid_at else None,
        )
        for p in result.scalars().all()
    ]
```

Add the schema names (`SubscriptionOut`, `PaymentOut`) to the `from quantuum.api.schemas import ...` line.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_billing_me.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/api/schemas.py src/quantuum/api/routes/me.py tests/test_api_billing_me.py
git commit -m "feat(3a): customer read API — GET /v1/me/subscriptions + /v1/me/payments"
```

---

### Task 9: Superadmin plan management API

**Files:**
- Create: `src/quantuum/api/routes/billing.py`
- Modify: `src/quantuum/api/schemas.py`, `src/quantuum/api/app.py`
- Test: `tests/test_api_admin_plans.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_admin_plans.py`:

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
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, None, True)}"}


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)}"}


async def test_create_and_list_subscription_plan(client, sa_headers):
    r = await client.post(
        "/admin/platform/plans/subscriptions",
        json={"slug": "annual", "name": "Annual", "period_days": 365, "price_cents": 2500},
        headers=sa_headers,
    )
    assert r.status_code == 201
    assert r.json()["slug"] == "annual"

    lst = await client.get("/admin/platform/plans/subscriptions", headers=sa_headers)
    assert lst.status_code == 200
    assert any(p["slug"] == "annual" for p in lst.json())


async def test_create_and_patch_package_plan(client, sa_headers):
    created = await client.post(
        "/admin/platform/plans/packages",
        json={"slug": "mega", "name": "Mega", "request_count": 100, "price_cents": 5000},
        headers=sa_headers,
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]

    patched = await client.patch(
        f"/admin/platform/plans/packages/{plan_id}",
        json={"price_cents": 4500, "active": False},
        headers=sa_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["price_cents"] == 4500
    assert patched.json()["active"] is False


async def test_customer_cannot_manage_plans(client, customer_headers):
    r = await client.get("/admin/platform/plans/subscriptions", headers=customer_headers)
    assert r.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_admin_plans.py -v`
Expected: FAIL — 404 (router not wired).

- [ ] **Step 3: Add schemas**

In `src/quantuum/api/schemas.py`, append:

```python
class SubscriptionPlanCreateIn(BaseModel):
    slug: str
    name: str
    period_days: int
    price_cents: int
    currency: str = "XTR"
    tenant_id: int | None = None


class PackagePlanCreateIn(BaseModel):
    slug: str
    name: str
    request_count: int
    price_cents: int
    currency: str = "XTR"
    expires_after_days: int | None = None
    tenant_id: int | None = None


class SubscriptionPlanPatchIn(BaseModel):
    name: str | None = None
    period_days: int | None = None
    price_cents: int | None = None
    active: bool | None = None


class PackagePlanPatchIn(BaseModel):
    name: str | None = None
    request_count: int | None = None
    price_cents: int | None = None
    expires_after_days: int | None = None
    active: bool | None = None


class SubscriptionPlanAdminOut(SubscriptionPlanOut):
    active: bool
    tenant_id: int | None


class PackagePlanAdminOut(PackagePlanOut):
    active: bool
    tenant_id: int | None
```

- [ ] **Step 4: Implement routes**

Create `src/quantuum/api/routes/billing.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_superadmin
from quantuum.api.schemas import (
    PackagePlanAdminOut,
    PackagePlanCreateIn,
    PackagePlanPatchIn,
    SubscriptionPlanAdminOut,
    SubscriptionPlanCreateIn,
    SubscriptionPlanPatchIn,
)
from quantuum.db.models import Account, PackagePlan, SubscriptionPlan

router = APIRouter(prefix="/admin/platform/plans", tags=["admin-plans"])


def _sub_out(p: SubscriptionPlan) -> SubscriptionPlanAdminOut:
    return SubscriptionPlanAdminOut(
        id=p.id, slug=p.slug, name=p.name, period_days=p.period_days,
        price_cents=p.price_cents, currency=p.currency, active=p.active, tenant_id=p.tenant_id,
    )


def _pkg_out(p: PackagePlan) -> PackagePlanAdminOut:
    return PackagePlanAdminOut(
        id=p.id, slug=p.slug, name=p.name, request_count=p.request_count,
        price_cents=p.price_cents, currency=p.currency, expires_after_days=p.expires_after_days,
        active=p.active, tenant_id=p.tenant_id,
    )


@router.post("/subscriptions", response_model=SubscriptionPlanAdminOut, status_code=201)
async def create_subscription_plan(
    body: SubscriptionPlanCreateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionPlanAdminOut:
    plan = SubscriptionPlan(
        tenant_id=body.tenant_id, slug=body.slug, name=body.name,
        period_days=body.period_days, price_cents=body.price_cents, currency=body.currency,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _sub_out(plan)


@router.get("/subscriptions", response_model=list[SubscriptionPlanAdminOut])
async def list_all_subscription_plans(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionPlanAdminOut]:
    result = await session.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.id))
    return [_sub_out(p) for p in result.scalars().all()]


@router.patch("/subscriptions/{plan_id}", response_model=SubscriptionPlanAdminOut)
async def patch_subscription_plan(
    plan_id: int,
    body: SubscriptionPlanPatchIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionPlanAdminOut:
    plan = await session.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _sub_out(plan)


@router.post("/packages", response_model=PackagePlanAdminOut, status_code=201)
async def create_package_plan(
    body: PackagePlanCreateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PackagePlanAdminOut:
    plan = PackagePlan(
        tenant_id=body.tenant_id, slug=body.slug, name=body.name,
        request_count=body.request_count, price_cents=body.price_cents,
        currency=body.currency, expires_after_days=body.expires_after_days,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _pkg_out(plan)


@router.get("/packages", response_model=list[PackagePlanAdminOut])
async def list_all_package_plans(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[PackagePlanAdminOut]:
    result = await session.execute(select(PackagePlan).order_by(PackagePlan.id))
    return [_pkg_out(p) for p in result.scalars().all()]


@router.patch("/packages/{plan_id}", response_model=PackagePlanAdminOut)
async def patch_package_plan(
    plan_id: int,
    body: PackagePlanPatchIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PackagePlanAdminOut:
    plan = await session.get(PackagePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return _pkg_out(plan)
```

- [ ] **Step 5: Wire router**

In `src/quantuum/api/app.py`, add `billing` to the routes import and `app.include_router(billing.router)`.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_api_admin_plans.py -v`
Expected: PASS (incl. the customer-403 test).

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/api/routes/billing.py src/quantuum/api/schemas.py src/quantuum/api/app.py tests/test_api_admin_plans.py
git commit -m "feat(3a): superadmin plan management API (/admin/platform/plans)"
```

---

## Self-Review (run before execution)

**Spec coverage (§4 Billing, §7 Plans):**
- `subscription_plans`, `package_plans` (global + tenant) ✓ (Tasks 1, 3) — UNION with tenant override in `list_*_plans`.
- `payment_providers`, `payments` (with JSONB metadata, idempotent mark-paid by external_id) ✓ (Tasks 2, 4).
- `account_subscriptions` (partial unique on active/grace per plan), `account_packages` (FIFO expiry ledger) ✓ (Task 2).
- Crediting: `apply_subscription_payment` (create/renew, extend `ends_at`), `apply_package_payment`, `recompute_account_balance` ✓ (Task 5).
- `consume_quota`/`refund_quota` keep the package ledger and `account_balance` in lockstep, oldest-expiring first ✓ (Task 6).
- Plan seeding (1 sub + 2 packages, placeholder prices) ✓ (Task 3).
- Customer read API: balance, plans, subscriptions, payments ✓ (Tasks 7, 8).
- Superadmin plan CRUD ✓ (Task 9).

**Deferred to Plan 3b (not defects):** PaymentProvider Protocol + TgStarsProvider; the bot Stars purchase flow (send_invoice/pre_checkout/successful_payment); API `POST /v1/me/subscriptions|packages` (via abstraction → 501); subscription lifecycle sweep (grace/expire) + renewal reminders; `payouts` + `tenant_licenses` tables and payout endpoints; `payment_providers` seeding for the platform tenant.

**Deliberate spec deviations:** `period_days`/`expires_after_days` ints instead of interval/text; `price_cents` = integer Star amount for XTR. Documented in scope notes.

**Placeholder scan:** none — all code complete; migrations use concrete handwritten revisions chained `a2b1c0d9e8f7 → b1a2c3d4e5f6 → c2b3d4e5f6a7`.

**Type/name consistency:** `apply_subscription_payment`/`apply_package_payment`/`recompute_account_balance`/`record_pending_payment`/`mark_payment_paid` signatures consistent across `billing.py` and tests. `list_subscription_plans`/`list_package_plans(session, *, tenant_id=)` used consistently in domain, seeding, and API. `consume_quota` package branch and `_oldest_valid_package` ordering match the FIFO test.
