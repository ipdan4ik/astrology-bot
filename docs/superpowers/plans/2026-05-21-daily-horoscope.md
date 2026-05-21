# Daily Horoscope Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A transit-aware daily horoscope delivered as a short Telegram message at each user's chosen local hour — a free subscriber perk, scheduled via an hourly dispatcher cron that fans out per-user generation tasks.

**Architecture:** Reuse the shipped `compute_transits` engine with a 3-day look-ahead and a new compact `render_daily_md` grounding; a new short LLM prompt narrates it. An hourly `daily_dispatch` cron selects due subscribers (enabled, active subscription, local hour == their `send_hour`, not-sent-today) and enqueues a per-user `daily_generate(account_id)` task that computes, narrates, stores, marks sent, and delivers via the user's tenant bot. Settings + history live in two new tables. Everything mirrors the qa/transits sub-projects.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3, SQLModel (async SQLAlchemy 2 + Pydantic v2), Alembic, arq (cron + functions), pytest + pytest-asyncio (auto mode), `zoneinfo`. Run tests with `uv run pytest`, lint with `uv run ruff check .`.

**Spec:** `docs/superpowers/specs/2026-05-21-daily-horoscope-design.md`.

**Branch:** already on `feat/daily-horoscope`.

---

## File Structure

- Create `src/quantuum/domain/daily.py` — settings CRUD, `is_subscriber`, `due_daily_account_ids`, horoscope claim/status/list, `mark_sent`, `get_tg_chat_id`.
- Create `src/quantuum/llm/daily_horoscope.py` + `src/quantuum/llm/prompts/daily_astrologer.txt` — grounded short narration.
- Create `src/quantuum/tasks/daily.py` — `daily_generate` task, `daily_dispatch` cron, `deliver_daily`.
- Create `src/quantuum/bot/handlers/daily.py` — `/daily` command + settings view + toggle/hour callbacks.
- Create `alembic/versions/d9e0f1a2b3c4_daily_tables.py` — `daily_subscriptions` + `daily_horoscopes`.
- Modify `src/quantuum/db/models.py` — `DailySubscription`, `DailyHoroscope`.
- Modify `src/quantuum/astrology/transits.py` — append `render_daily_md`.
- Modify `src/quantuum/domain/tenants.py` — add `get_active_tenant_bot`.
- Modify `src/quantuum/tasks/enqueue.py` — `enqueue_daily`.
- Modify `src/quantuum/tasks/worker.py` — register `daily_generate` + `daily_dispatch` cron.
- Modify `src/quantuum/api/schemas.py` + `src/quantuum/api/routes/me.py` — daily settings + history routes.
- Modify `src/quantuum/bot/ui/callbacks.py` (`DailyCb`), `bot/ui/text.py`, `bot/ui/keyboards.py`, `bot/handlers/menu.py`, `bot/app.py`, `i18n/seed_strings.py`.
- Tests: `tests/test_daily_models.py`, `tests/test_daily_domain.py`, `tests/test_daily_horoscope_llm.py`, `tests/test_task_daily.py`, `tests/test_daily_dispatch.py`, `tests/test_api_daily.py`, `tests/test_daily_bot.py`; append to `tests/test_transits_engine.py`; modify `tests/test_ui_keyboards.py`, `tests/test_bot_start_menu_profile.py`.

---

## Task 1: Models + migration

**Files:**
- Modify: `src/quantuum/db/models.py` (add `DailySubscription` + `DailyHoroscope` after `TransitReport`, before `class Request`)
- Create: `alembic/versions/d9e0f1a2b3c4_daily_tables.py`
- Test: `tests/test_daily_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_models.py
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import DailyHoroscope, DailySubscription, NatalProfile


async def _acc_profile(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="11")
    profile = NatalProfile(
        tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
        birth_date=date(1990, 6, 15), birth_time=time(14, 30), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6176"), timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


async def test_daily_subscription_defaults(session, default_tenant):
    acc, _ = await _acc_profile(session, default_tenant.id)
    row = DailySubscription(account_id=acc.id, tenant_id=default_tenant.id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.enabled is False
    assert row.send_hour == 9
    assert row.last_sent_on is None
    assert row.created_at is not None


async def test_daily_horoscope_unique_per_day(session, default_tenant):
    acc, profile = await _acc_profile(session, default_tenant.id)
    a = DailyHoroscope(
        tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
        local_date=date(2026, 3, 1), lang="ru",
    )
    session.add(a)
    await session.commit()
    assert a.status == "generating"

    b = DailyHoroscope(
        tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
        local_date=date(2026, 3, 1), lang="ru",
    )
    session.add(b)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_daily_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'DailySubscription'`.

- [ ] **Step 3: Add the models**

In `src/quantuum/db/models.py`, immediately after the `TransitReport` class (before `class Request`), add. (`date`, `datetime`, `Index`, `UniqueConstraint`, `Field`, `SQLModel`, `_dt_field`, `utcnow` are all already imported at the top of this module.)

```python
class DailySubscription(SQLModel, table=True):
    __tablename__ = "daily_subscriptions"

    account_id: int = Field(foreign_key="accounts.id", primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    enabled: bool = False
    send_hour: int = 9  # user's preferred LOCAL hour, 0-23
    last_sent_on: date | None = None  # user's local date of last successful send
    created_at: datetime = _dt_field(default_factory=utcnow)
    updated_at: datetime = _dt_field(default_factory=utcnow)


class DailyHoroscope(SQLModel, table=True):
    __tablename__ = "daily_horoscopes"
    __table_args__ = (
        Index("ix_daily_horoscopes_tenant_created", "tenant_id", "created_at"),
        UniqueConstraint("account_id", "local_date", name="uq_daily_horoscope_account_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    local_date: date
    transit_md: str | None = None
    horoscope_md: str | None = None
    lang: str | None = None
    status: str = "generating"  # generating|done|failed
    error: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_daily_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Create the migration**

First confirm the current head: `uv run alembic heads` → expect `c8d9e0f1a2b3 (head)`.

Create `alembic/versions/d9e0f1a2b3c4_daily_tables.py`:

```python
"""daily_subscriptions + daily_horoscopes

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-21 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_subscriptions",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("send_hour", sa.Integer(), nullable=False),
        sa.Column("last_sent_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_index("ix_daily_subscriptions_tenant_id", "daily_subscriptions", ["tenant_id"])

    op.create_table(
        "daily_horoscopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("natal_profile_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("transit_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("horoscope_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_tokens_in", sa.Integer(), nullable=True),
        sa.Column("llm_tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["natal_profile_id"], ["natal_profiles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "local_date", name="uq_daily_horoscope_account_date"),
    )
    op.create_index("ix_daily_horoscopes_account_id", "daily_horoscopes", ["account_id"])
    op.create_index("ix_daily_horoscopes_tenant_id", "daily_horoscopes", ["tenant_id"])
    op.create_index("ix_daily_horoscopes_tenant_created", "daily_horoscopes", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_daily_horoscopes_tenant_created", table_name="daily_horoscopes")
    op.drop_index("ix_daily_horoscopes_tenant_id", table_name="daily_horoscopes")
    op.drop_index("ix_daily_horoscopes_account_id", table_name="daily_horoscopes")
    op.drop_table("daily_horoscopes")
    op.drop_index("ix_daily_subscriptions_tenant_id", table_name="daily_subscriptions")
    op.drop_table("daily_subscriptions")
```

- [ ] **Step 6: Verify single head + offline SQL**

Run: `uv run alembic heads` → expect a single head `d9e0f1a2b3c4 (head)`.
Run: `uv run alembic upgrade head --sql > /dev/null && echo OK` → expect `OK`.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/d9e0f1a2b3c4_daily_tables.py tests/test_daily_models.py
git commit -m "feat(daily): DailySubscription + DailyHoroscope models + migration"
```

---

## Task 2: render_daily_md (compact daily grounding)

**Files:**
- Modify: `src/quantuum/astrology/transits.py` (append `render_daily_md` at the end)
- Test: `tests/test_transits_engine.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transits_engine.py` (the file already imports `datetime, timedelta, timezone` at the top from Task 3 of the transits plan):

```python
def test_render_daily_md_active_and_imminent():
    from quantuum.astrology.transits import (
        ActiveAspect,
        SkyPosition,
        TransitHit,
        TransitReport,
        render_daily_md,
    )

    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    act = ActiveAspect(body="Saturn", target="Sun", aspect="Square", orb=1.2,
                       applying=True, exact_at=as_of + timedelta(days=2))
    near = TransitHit(body="Mars", target="Venus", aspect="Trine",
                      exact_at=as_of + timedelta(days=2), retrograde=False)
    far = TransitHit(body="Jupiter", target="Moon", aspect="Sextile",
                     exact_at=as_of + timedelta(days=10), retrograde=False)
    report = TransitReport(
        as_of=as_of, window_days=7,
        sky=[SkyPosition(body="Sun", longitude=1.0, retrograde=False)],
        active=[act], upcoming=[near, far],
    )
    md = render_daily_md(report, ahead_days=3)
    assert "## Active now" in md
    assert "Saturn" in md and "applying" in md and "1.20" in md
    assert "Mars" in md and "2026-03-03" in md   # imminent (<= 3 days) included
    assert "Jupiter" not in md                    # 10 days out -> excluded
    assert "## Exact within 3 days" in md


def test_render_daily_md_empty():
    from quantuum.astrology.transits import TransitReport, render_daily_md

    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    report = TransitReport(as_of=as_of, window_days=7, sky=[], active=[], upcoming=[])
    md = render_daily_md(report)
    assert "_No active transits._" in md
    assert "_None._" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transits_engine.py -k render_daily -v`
Expected: FAIL with `ImportError: cannot import name 'render_daily_md'`.

- [ ] **Step 3: Implement render_daily_md**

Append to `src/quantuum/astrology/transits.py` (`timedelta` and `to_fixed` are already imported in this module):

```python
def render_daily_md(report: TransitReport, *, ahead_days: int = 3) -> str:
    """Compact daily grounding: active aspects now + exacts within *ahead_days*.

    Distinct from render_transits_md (the full 90-day 3-table report). Used to
    ground the short daily-horoscope narration.
    """
    cutoff = report.as_of + timedelta(days=ahead_days)
    lines: list[str] = []

    lines.append("## Active now")
    lines.append("")
    if not report.active:
        lines.append("_No active transits._")
    else:
        lines.append("| Transit | Aspect | Natal | Orb | Phase |")
        lines.append("| --- | --- | --- | --- | --- |")
        for a in report.active:
            phase = "applying" if a.applying else "separating"
            lines.append(f"| {a.body} | {a.aspect} | {a.target} | {to_fixed(a.orb, 2)}° | {phase} |")
    lines.append("")

    lines.append(f"## Exact within {ahead_days} days")
    lines.append("")
    imminent = [h for h in report.upcoming if h.exact_at <= cutoff]
    if not imminent:
        lines.append("_None._")
    else:
        lines.append("| Date | Transit | Aspect | Natal |")
        lines.append("| --- | --- | --- | --- |")
        for h in imminent:
            lines.append(f"| {h.exact_at.strftime('%Y-%m-%d')} | {h.body} | {h.aspect} | {h.target} |")
    lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests + lint**

Run: `uv run pytest tests/test_transits_engine.py -k render_daily -v` → PASS (2).
Run: `uv run ruff check src/quantuum/astrology/transits.py tests/test_transits_engine.py` → `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/transits.py tests/test_transits_engine.py
git commit -m "feat(daily): render_daily_md compact grounding (active + imminent exacts)"
```

---

## Task 3: domain/daily.py

**Files:**
- Create: `src/quantuum/domain/daily.py`
- Test: `tests/test_daily_domain.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_daily_domain.py
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, NatalProfile
from quantuum.domain.daily import (
    claim_horoscope,
    due_daily_account_ids,
    get_settings,
    get_tg_chat_id,
    is_subscriber,
    list_horoscopes,
    mark_sent,
    set_horoscope_status,
    upsert_settings,
)


async def _account(session, tenant_id, tg_user_id, *, tz="Europe/Moscow", subscriber=True):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg_user_id)
    session.add(NatalProfile(
        tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone=tz,
    ))
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    return acc


async def test_is_subscriber(session, default_tenant):
    sub = await _account(session, default_tenant.id, "1", subscriber=True)
    non = await _account(session, default_tenant.id, "2", subscriber=False)
    assert await is_subscriber(session, sub.id) is True
    assert await is_subscriber(session, non.id) is False


async def test_upsert_and_get_settings(session, default_tenant):
    acc = await _account(session, default_tenant.id, "3")
    assert await get_settings(session, acc.id) is None
    row = await upsert_settings(
        session, tenant_id=default_tenant.id, account_id=acc.id, enabled=True, send_hour=8
    )
    assert row.enabled is True and row.send_hour == 8
    again = await upsert_settings(
        session, tenant_id=default_tenant.id, account_id=acc.id, enabled=True, send_hour=21
    )
    assert again.send_hour == 21
    fetched = await get_settings(session, acc.id)
    assert fetched.send_hour == 21


async def test_claim_horoscope_is_idempotent(session, default_tenant):
    acc = await _account(session, default_tenant.id, "4")
    profile = (await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == acc.id)
    )).scalars().first()
    first = await claim_horoscope(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, local_date=date(2026, 3, 1), lang="ru",
    )
    assert first is not None and first.status == "generating"
    second = await claim_horoscope(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, local_date=date(2026, 3, 1), lang="ru",
    )
    assert second is None


async def test_set_status_and_list(session, default_tenant):
    acc = await _account(session, default_tenant.id, "5")
    profile = (await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == acc.id)
    )).scalars().first()
    r1 = await claim_horoscope(session, tenant_id=default_tenant.id, account_id=acc.id,
                               natal_profile_id=profile.id, local_date=date(2026, 3, 1), lang="ru")
    r2 = await claim_horoscope(session, tenant_id=default_tenant.id, account_id=acc.id,
                               natal_profile_id=profile.id, local_date=date(2026, 3, 2), lang="ru")
    await set_horoscope_status(session, r1.id, "done", horoscope_md="hi", llm_tokens_in=3)
    await session.refresh(r1)
    assert r1.status == "done" and r1.horoscope_md == "hi" and r1.completed_at is not None
    rows = await list_horoscopes(session, account_id=acc.id)
    assert [r.id for r in rows] == [r2.id, r1.id]  # newest-first


async def test_mark_sent(session, default_tenant):
    acc = await _account(session, default_tenant.id, "6")
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=acc.id, enabled=True, send_hour=9)
    await mark_sent(session, acc.id, date(2026, 3, 1))
    settings = await get_settings(session, acc.id)
    assert settings.last_sent_on == date(2026, 3, 1)


async def test_get_tg_chat_id(session, default_tenant):
    acc = await _account(session, default_tenant.id, "777")
    chat = await get_tg_chat_id(session, acc.id)
    assert chat == "777"  # find_or_create_account_by_tg stored provider_user_id="777"


async def test_due_daily_account_ids_selection(session, default_tenant):
    # now = 06:00 UTC -> Moscow (UTC+3) local 09:00.
    now = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)

    due_acc = await _account(session, default_tenant.id, "10", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=due_acc.id, enabled=True, send_hour=9)

    wrong_hour = await _account(session, default_tenant.id, "11", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=wrong_hour.id, enabled=True, send_hour=10)

    already = await _account(session, default_tenant.id, "12", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=already.id, enabled=True, send_hour=9)
    await mark_sent(session, already.id, date(2026, 3, 1))  # already sent today (local)

    non_sub = await _account(session, default_tenant.id, "13", tz="Europe/Moscow", subscriber=False)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=non_sub.id, enabled=True, send_hour=9)

    disabled = await _account(session, default_tenant.id, "14", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=disabled.id, enabled=False, send_hour=9)

    due = await due_daily_account_ids(session, now=now)
    assert due_acc.id in due
    assert wrong_hour.id not in due
    assert already.id not in due
    assert non_sub.id not in due
    assert disabled.id not in due
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daily_domain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.domain.daily'`.

- [ ] **Step 3: Implement the domain module**

Create `src/quantuum/domain/daily.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AccountIdentity,
    DailyHoroscope,
    DailySubscription,
    NatalProfile,
)

_TERMINAL = {"done", "failed"}


async def is_subscriber(session, account_id: int) -> bool:
    bal = await session.get(AccountBalance, account_id)
    return bal is not None and bal.subscription_active_until is not None and (
        bal.subscription_active_until > utcnow()
    )


async def get_settings(session, account_id: int) -> DailySubscription | None:
    return await session.get(DailySubscription, account_id)


async def upsert_settings(
    session, *, tenant_id: int, account_id: int, enabled: bool, send_hour: int
) -> DailySubscription:
    row = await session.get(DailySubscription, account_id)
    if row is None:
        row = DailySubscription(account_id=account_id, tenant_id=tenant_id)
    row.tenant_id = tenant_id
    row.enabled = enabled
    row.send_hour = send_hour
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def mark_sent(session, account_id: int, local_date: date) -> None:
    row = await session.get(DailySubscription, account_id)
    if row is None:
        return
    row.last_sent_on = local_date
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()


async def claim_horoscope(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int,
    local_date: date, lang: str | None,
) -> DailyHoroscope | None:
    """Insert a generating row for (account_id, local_date). Returns None if one already exists."""
    row = DailyHoroscope(
        tenant_id=tenant_id, account_id=account_id, natal_profile_id=natal_profile_id,
        local_date=local_date, lang=lang, status="generating",
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    await session.refresh(row)
    return row


async def set_horoscope_status(session, horoscope_id: int, status: str, **fields) -> None:
    row = await session.get(DailyHoroscope, horoscope_id)
    if row is None:
        return
    row.status = status
    for key, value in fields.items():
        setattr(row, key, value)
    if status in _TERMINAL:
        row.completed_at = utcnow()
    session.add(row)
    await session.commit()


async def list_horoscopes(
    session, *, account_id: int, limit: int = 30, offset: int = 0
) -> list[DailyHoroscope]:
    result = await session.execute(
        select(DailyHoroscope)
        .where(DailyHoroscope.account_id == account_id)
        .order_by(DailyHoroscope.created_at.desc(), DailyHoroscope.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_tg_chat_id(session, account_id: int) -> str | None:
    result = await session.execute(
        select(AccountIdentity.provider_user_id).where(
            AccountIdentity.account_id == account_id,
            AccountIdentity.provider == "tg_chat",
        )
    )
    return result.scalars().first()


async def due_daily_account_ids(session, *, now: datetime) -> list[int]:
    """Account ids whose daily horoscope is due at *now* (tz-aware UTC).

    Eligible: enabled, active subscription, has a natal profile (timezone), the
    user's current LOCAL hour equals send_hour, and not already sent today (local).
    """
    result = await session.execute(
        select(DailySubscription, NatalProfile.timezone)
        .join(NatalProfile, NatalProfile.account_id == DailySubscription.account_id)
        .join(AccountBalance, AccountBalance.account_id == DailySubscription.account_id)
        .where(
            DailySubscription.enabled == True,  # noqa: E712
            AccountBalance.subscription_active_until.is_not(None),
            AccountBalance.subscription_active_until > now,
        )
    )
    due: list[int] = []
    for sub, tz_name in result.all():
        try:
            local = now.astimezone(ZoneInfo(tz_name))
        except Exception:
            continue
        if local.hour != sub.send_hour:
            continue
        if sub.last_sent_on is not None and sub.last_sent_on >= local.date():
            continue
        due.append(sub.account_id)
    return due
```

- [ ] **Step 4: Run tests + lint**

Run: `uv run pytest tests/test_daily_domain.py -v` → PASS (7).
Run: `uv run ruff check src/quantuum/domain/daily.py tests/test_daily_domain.py` → `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/daily.py tests/test_daily_domain.py
git commit -m "feat(daily): domain (settings, eligibility, due-selection, claim, history)"
```

---

## Task 4: llm/daily_horoscope.py + prompt

**Files:**
- Create: `src/quantuum/llm/daily_horoscope.py`
- Create: `src/quantuum/llm/prompts/daily_astrologer.txt`
- Test: `tests/test_daily_horoscope_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_horoscope_llm.py
from quantuum.llm.base import LLMResult
from quantuum.llm.daily_horoscope import daily_horoscope


class CaptureLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.system = system
        self.user = user
        return LLMResult(text="BLURB", tokens_in=1, tokens_out=2, model=model)


async def test_daily_horoscope_wraps_inputs():
    client = CaptureLLM()
    result = await daily_horoscope(
        client, "NATAL_MD", "TRANSIT_MD", lang="ru",
        model="claude-x", temperature=0.5, max_tokens=300,
    )
    assert result.text == "BLURB"
    assert client.system and "horoscope" in client.system.lower()
    assert "NATAL CHART:" in client.user and "NATAL_MD" in client.user
    assert "TRANSITS:" in client.user and "TRANSIT_MD" in client.user
    assert "Answer in language: ru." in client.user
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_daily_horoscope_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.llm.daily_horoscope'`.

- [ ] **Step 3: Create the prompt + module**

Create `src/quantuum/llm/prompts/daily_astrologer.txt`:

```
You are Quantuum's grounded daily-horoscope astrologer. You write ONE short daily horoscope for a person about their own chart today.

You will receive two Markdown documents produced by a deterministic calculator: the person's natal chart, and a compact transit table (transits active today and any exact transits in the next few days). These are the only allowed facts. Treat them as the complete and only source of truth.

CRITICAL FACT RULES
- Use ONLY facts present in the provided natal chart and transit table.
- Never invent, alter, or "correct" any placement, aspect, planet, sign, house, number, or date. If the table says it, use it exactly. If it does not, do not claim it.
- Do not introduce transits, aspects, or dates that are not in the table.
- If there are no active transits and nothing exact soon, say plainly that the sky is quiet for them today.

STYLE
- Write 2 to 5 warm, practical sentences. Speak directly to the person as "you".
- Lead with the most significant contact (tighter orbs and slower planets matter most); name the transit-to-natal aspect you build each point on.
- No headings, no lists, no filler. It should read like a short morning note.

LANGUAGE AND OUTPUT
- Answer in the language requested in the user message.
- Return plain text / light Markdown only. No process notes, no disclaimers, no "based on the data".
- Do not mention being an AI, an LLM, or a model. Do not cite websites, books, or sources.
```

Create `src/quantuum/llm/daily_horoscope.py` (mirrors `llm/transit_report.py`):

```python
from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "daily_astrologer.txt"


async def daily_horoscope(client, natal_md, transit_md, *, lang, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Write today's short horoscope for this person using ONLY the natal chart and the transit table below.",
            f"Answer in language: {lang}.",
            "",
            "NATAL CHART:",
            natal_md,
            "",
            "TRANSITS:",
            transit_md,
        ]
    )
    return await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

- [ ] **Step 4: Run test + lint**

Run: `uv run pytest tests/test_daily_horoscope_llm.py -v` → PASS.
Run: `uv run ruff check src/quantuum/llm/daily_horoscope.py tests/test_daily_horoscope_llm.py` → `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/llm/daily_horoscope.py src/quantuum/llm/prompts/daily_astrologer.txt tests/test_daily_horoscope_llm.py
git commit -m "feat(daily): grounded daily-horoscope LLM prompt + wrapper"
```

---

## Task 5: daily_generate task + delivery + enqueue + worker function

**Files:**
- Modify: `src/quantuum/domain/tenants.py` (add `get_active_tenant_bot`)
- Create: `src/quantuum/tasks/daily.py` (`daily_generate`, `deliver_daily`)
- Modify: `src/quantuum/tasks/enqueue.py` (add `enqueue_daily`)
- Modify: `src/quantuum/tasks/worker.py` (import + register `daily_generate`)
- Test: `tests/test_task_daily.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_task_daily.py
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, DailyHoroscope, DailySubscription, NatalProfile
from quantuum.domain.daily import upsert_settings
from quantuum.llm.base import LLMResult
from quantuum.tasks.daily import daily_generate


class FakeLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        return LLMResult(text="DAILY BLURB", tokens_in=5, tokens_out=9, model="claude-test")


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, s):
        self._s = s

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


async def _setup(session, tenant_id, tg="42", *, subscriber=True, profile=True, enabled=True):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    if profile:
        session.add(NatalProfile(
            tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
            birth_date=date(1990, 6, 15), birth_time=time(14, 30), birth_place="Moscow",
            latitude=Decimal("55.7558"), longitude=Decimal("37.6176"), timezone="Europe/Moscow",
        ))
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    if enabled:
        await upsert_settings(session, tenant_id=tenant_id, account_id=acc.id, enabled=True, send_hour=9)
    return acc


async def test_daily_generate_happy(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id)

    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}
    await daily_generate(ctx, acc.id)

    rows = (await session.execute(select(DailyHoroscope).where(DailyHoroscope.account_id == acc.id))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "done"
    assert row.horoscope_md == "DAILY BLURB"
    assert row.transit_md and "Active now" in row.transit_md
    assert row.llm_tokens_in == 5 and row.llm_provider == "anthropic"
    settings = await session.get(DailySubscription, acc.id)
    assert settings.last_sent_on is not None
    deliver.assert_awaited_once()


async def test_daily_generate_already_sent_skips(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id)
    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}

    await daily_generate(ctx, acc.id)
    await daily_generate(ctx, acc.id)  # second call same day -> claim returns None

    rows = (await session.execute(select(DailyHoroscope).where(DailyHoroscope.account_id == acc.id))).scalars().all()
    assert len(rows) == 1
    deliver.assert_awaited_once()


async def test_daily_generate_not_subscriber_skips(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id, subscriber=False)
    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}

    await daily_generate(ctx, acc.id)
    rows = (await session.execute(select(DailyHoroscope))).scalars().all()
    assert rows == []
    deliver.assert_not_awaited()


async def test_daily_generate_no_profile_skips(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id, profile=False)
    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}

    await daily_generate(ctx, acc.id)
    assert (await session.execute(select(DailyHoroscope))).scalars().first() is None
    deliver.assert_not_awaited()


async def test_daily_generate_llm_failure_marks_failed_no_delivery(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id)
    ctx = {"sessionmaker": _Maker(session), "llm_client": None}  # no LLM -> failure path

    await daily_generate(ctx, acc.id)
    row = (await session.execute(select(DailyHoroscope).where(DailyHoroscope.account_id == acc.id))).scalars().first()
    assert row.status == "failed"
    settings = await session.get(DailySubscription, acc.id)
    assert settings.last_sent_on is not None  # day skipped even on failure
    deliver.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_task_daily.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.tasks.daily'`.

- [ ] **Step 3: Add `get_active_tenant_bot`**

In `src/quantuum/domain/tenants.py`, after `list_active_tenant_bots`, add:

```python
async def get_active_tenant_bot(session, tenant_id: int) -> TenantBot | None:
    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id, TenantBot.status == "active")
    )
    return result.scalars().first()
```

(`TenantBot` and `select` are already imported in this module.)

- [ ] **Step 4: Create the task**

Create `src/quantuum/tasks/daily.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from quantuum.astrology.transits import compute_transits, render_daily_md
from quantuum.common.crypto import decrypt_token
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account
from quantuum.domain.daily import (
    claim_horoscope,
    get_settings,
    get_tg_chat_id,
    is_subscriber,
    mark_sent,
    set_horoscope_status,
)
from quantuum.domain.llm_config import get_llm_config
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.tenants import get_active_tenant_bot
from quantuum.domain.transits import resolve_natal
from quantuum.i18n import Translator
from quantuum.llm.daily_horoscope import daily_horoscope
from quantuum.logging_setup import get_logger
from quantuum.tasks.enqueue import enqueue_daily

logger = get_logger("task.daily")


async def deliver_daily(sessionmaker, *, tenant_id: int, chat_id: str, lang: str | None, text: str) -> None:
    """Send the horoscope via the user's tenant bot. Best-effort."""
    async with sessionmaker() as session:
        tb = await get_active_tenant_bot(session, tenant_id)
        if tb is None:
            return
        i18n = await Translator.build(
            session, tenant_id=tenant_id, preferred_lang=lang, tg_language_code=None
        )
        header = await i18n("daily.header")
    bot = Bot(token=decrypt_token(tb.bot_token_enc))
    try:
        await bot.send_message(int(chat_id), f"{header}\n\n{text}"[:4000])
    finally:
        await bot.session.close()


async def daily_generate(ctx, account_id: int) -> None:
    sessionmaker = ctx["sessionmaker"]
    deliver: tuple[int, str, str | None, str] | None = None

    async with sessionmaker() as session:
        account = await session.get(Account, account_id)
        if account is None:
            return
        if not await is_subscriber(session, account_id):
            return
        profile = await get_natal_profile(session, account_id)
        if profile is None:
            return
        settings = await get_settings(session, account_id)
        if settings is None or not settings.enabled:
            return

        local_date = utcnow().astimezone(ZoneInfo(profile.timezone)).date()
        lang = account.preferred_lang or "ru"
        row = await claim_horoscope(
            session, tenant_id=account.tenant_id, account_id=account_id,
            natal_profile_id=profile.id, local_date=local_date, lang=lang,
        )
        if row is None:
            return  # already handled today

        try:
            inp, natal_md, _ = await resolve_natal(
                session, account_id=account_id, natal_profile_id=profile.id
            )
            report = compute_transits(inp, as_of=utcnow(), window_days=7)
            transit_md = render_daily_md(report, ahead_days=3)
            await set_horoscope_status(session, row.id, "generating", transit_md=transit_md)

            llm_client = ctx.get("llm_client")
            if llm_client is None:
                await set_horoscope_status(session, row.id, "failed", error="llm unavailable")
                await mark_sent(session, account_id, local_date)
                return

            cfg = await get_llm_config(session)
            result = await daily_horoscope(
                llm_client, natal_md, transit_md, lang=lang,
                model=cfg["model"], temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
            )
            await set_horoscope_status(
                session, row.id, "done",
                horoscope_md=result.text,
                llm_provider=cfg["provider"], llm_model=result.model,
                llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out,
            )
            await mark_sent(session, account_id, local_date)

            chat_id = await get_tg_chat_id(session, account_id)
            if chat_id is not None:
                deliver = (account.tenant_id, chat_id, lang, result.text)
        except Exception:
            logger.exception("daily_generation_failed", account_id=account_id)
            try:
                await set_horoscope_status(session, row.id, "failed", error="generation failed")
            except Exception:
                logger.exception("daily_set_failed_status_error", account_id=account_id)
            await mark_sent(session, account_id, local_date)
            return

    if deliver is not None:
        tenant_id, chat_id, lang, text = deliver
        try:
            await deliver_daily(sessionmaker, tenant_id=tenant_id, chat_id=chat_id, lang=lang, text=text)
        except Exception:
            logger.exception("daily_delivery_failed", account_id=account_id)

    logger.info("daily_generated", account_id=account_id)
```

CRITICAL: confirm names by reading the codebase before running — `get_llm_config(session)` returns a dict with keys `provider`/`model`/`temperature`/`max_tokens` (provider defaults to "anthropic"); `resolve_natal(session, *, account_id, natal_profile_id)` returns `(BlueprintInput, natal_md, blueprint_id)`; `get_logger` is imported from `quantuum.logging_setup`; `decrypt_token` lives in `quantuum.common.crypto`; `Translator.build(session, *, tenant_id, preferred_lang, tg_language_code)` is the real signature (see `tests/conftest.py::build_translator`). If any differ, adapt and report.

- [ ] **Step 5: Add the enqueue helper**

In `src/quantuum/tasks/enqueue.py`, after `enqueue_transit`, add:

```python
async def enqueue_daily(account_id: int) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("daily_generate", account_id)
```

- [ ] **Step 6: Register the worker function**

In `src/quantuum/tasks/worker.py`:
- Add this import after `from quantuum.tasks.transits import transit_generate` (only `daily_generate` for now — `daily_dispatch` does not exist until Task 6, which updates this same import line):
  ```python
  from quantuum.tasks.daily import daily_generate
  ```
- Append `daily_generate` to the `functions` list:
  ```python
      functions = [blueprint_generate, provision_tenant, subscription_lifecycle, qa_generate, transit_generate, daily_generate]
  ```

- [ ] **Step 7: Run tests + lint**

Run: `uv run pytest tests/test_task_daily.py -v` → PASS (5).
Run: `uv run ruff check src/quantuum/tasks/daily.py src/quantuum/tasks/enqueue.py src/quantuum/tasks/worker.py src/quantuum/domain/tenants.py tests/test_task_daily.py` → `All checks passed!`.

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/tasks/daily.py src/quantuum/tasks/enqueue.py src/quantuum/tasks/worker.py src/quantuum/domain/tenants.py tests/test_task_daily.py
git commit -m "feat(daily): daily_generate task + tenant-bot delivery + enqueue + worker function"
```

---

## Task 6: daily_dispatch cron

**Files:**
- Modify: `src/quantuum/tasks/daily.py` (add `daily_dispatch`)
- Modify: `src/quantuum/tasks/worker.py` (register the cron + import)
- Test: `tests/test_daily_dispatch.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_daily_dispatch.py
from unittest.mock import AsyncMock

from quantuum.tasks.daily import daily_dispatch


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, s):
        self._s = s

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


async def test_daily_dispatch_enqueues_due_accounts(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    async def fake_due(_session, *, now):
        return [101, 202]

    spy = AsyncMock()
    monkeypatch.setattr(daily_mod, "due_daily_account_ids", fake_due)
    monkeypatch.setattr(daily_mod, "enqueue_daily", spy)

    await daily_dispatch({"sessionmaker": _Maker(session)})

    assert spy.await_count == 2
    assert [c.args[0] for c in spy.await_args_list] == [101, 202]


async def test_daily_dispatch_no_due_enqueues_nothing(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    async def fake_due(_session, *, now):
        return []

    spy = AsyncMock()
    monkeypatch.setattr(daily_mod, "due_daily_account_ids", fake_due)
    monkeypatch.setattr(daily_mod, "enqueue_daily", spy)

    await daily_dispatch({"sessionmaker": _Maker(session)})
    spy.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daily_dispatch.py -v`
Expected: FAIL with `ImportError: cannot import name 'daily_dispatch'`.

- [ ] **Step 3: Implement the dispatcher**

Add to the imports at the top of `src/quantuum/tasks/daily.py` (next to the existing daily-domain imports):

```python
from quantuum.domain.daily import due_daily_account_ids
```

(Add `due_daily_account_ids` to the existing `from quantuum.domain.daily import (...)` block rather than a second import line.)

Append to `src/quantuum/tasks/daily.py`:

```python
async def daily_dispatch(ctx) -> None:
    """Hourly cron: enqueue a daily_generate job for every account due right now."""
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        account_ids = await due_daily_account_ids(session, now=utcnow())
    for account_id in account_ids:
        await enqueue_daily(account_id)
    logger.info("daily_dispatched", count=len(account_ids))
```

- [ ] **Step 4: Register the cron**

In `src/quantuum/tasks/worker.py`:
- Update the daily import to include the dispatcher:
  ```python
  from quantuum.tasks.daily import daily_dispatch, daily_generate
  ```
- Add the cron next to the existing one:
  ```python
      cron_jobs = [cron(subscription_lifecycle, minute=0), cron(daily_dispatch, minute=0)]
  ```

- [ ] **Step 5: Run tests + lint**

Run: `uv run pytest tests/test_daily_dispatch.py -v` → PASS (2).
Run: `uv run ruff check src/quantuum/tasks/daily.py src/quantuum/tasks/worker.py tests/test_daily_dispatch.py` → `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/tasks/daily.py src/quantuum/tasks/worker.py tests/test_daily_dispatch.py
git commit -m "feat(daily): daily_dispatch hourly cron + worker registration"
```

---

## Task 7: API routes + schemas

**Files:**
- Modify: `src/quantuum/api/schemas.py` (add daily schemas after `TransitOut`)
- Modify: `src/quantuum/api/routes/me.py` (imports + routes after the transit routes)
- Test: `tests/test_api_daily.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_daily.py
from datetime import date, time, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, DailyHoroscope, NatalProfile
from quantuum.domain.natal_profiles import upsert_natal_profile


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _account(session, tenant_id, tg="1", *, subscriber=False, profile=False):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    if profile:
        await upsert_natal_profile(
            session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
            birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
            latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
        )
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    return acc


def _headers(acc, tenant_id):
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, tenant_id, False)}"}


async def test_get_daily_defaults(client, session, default_tenant):
    acc = await _account(session, default_tenant.id)
    r = await client.get("/v1/me/daily", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["send_hour"] == 9 and body["last_sent_on"] is None


async def test_put_enable_requires_subscription(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=False)
    r = await client.put(
        "/v1/me/daily", json={"enabled": True, "send_hour": 8}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 403


async def test_put_enable_as_subscriber(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=True)
    r = await client.put(
        "/v1/me/daily", json={"enabled": True, "send_hour": 8}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True and r.json()["send_hour"] == 8


async def test_put_disable_allowed_for_non_subscriber(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=False)
    r = await client.put(
        "/v1/me/daily", json={"enabled": False, "send_hour": 9}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


async def test_put_bad_hour_422(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=True)
    r = await client.put(
        "/v1/me/daily", json={"enabled": True, "send_hour": 25}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 422


async def test_list_horoscopes_newest_first(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=True, profile=True)
    profile = (await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == acc.id)
    )).scalars().first()
    a = DailyHoroscope(tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
                       local_date=date(2026, 3, 1), status="done", horoscope_md="one")
    session.add(a)
    await session.commit()
    b = DailyHoroscope(tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
                       local_date=date(2026, 3, 2), status="done", horoscope_md="two")
    session.add(b)
    await session.commit()

    r = await client.get("/v1/me/daily/horoscopes", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [b.id, a.id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_daily.py -v`
Expected: FAIL (schemas/routes missing).

- [ ] **Step 3: Add the schemas**

In `src/quantuum/api/schemas.py`, after the `TransitOut` class, add. (`BaseModel` and `datetime` are already imported; `date` and `Field` may not be — add `date` to the existing `from datetime import ...` line and ensure `Field` is imported from pydantic, e.g. extend the existing `from pydantic import BaseModel` to `from pydantic import BaseModel, Field`.)

```python
class DailySettingsIn(BaseModel):
    enabled: bool
    send_hour: int = Field(ge=0, le=23)


class DailySettingsOut(BaseModel):
    enabled: bool
    send_hour: int
    last_sent_on: date | None


class DailyHoroscopeOut(BaseModel):
    id: int
    local_date: date
    horoscope_md: str | None
    status: str
    lang: str | None
    created_at: datetime
    completed_at: datetime | None
```

- [ ] **Step 4: Add the routes**

In `src/quantuum/api/routes/me.py`:
- Add to the `quantuum.api.schemas` import block: `DailySettingsIn`, `DailySettingsOut`, `DailyHoroscopeOut`.
- Add the domain import after the transits domain import:
  ```python
  from quantuum.domain.daily import get_settings, is_subscriber, list_horoscopes, upsert_settings
  ```

After the transit routes (after `read_transit_route`), add:

```python
def _daily_horoscope_out(row) -> DailyHoroscopeOut:
    return DailyHoroscopeOut(
        id=row.id,
        local_date=row.local_date,
        horoscope_md=row.horoscope_md,
        status=row.status,
        lang=row.lang,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.get("/daily", response_model=DailySettingsOut)
async def read_daily_settings(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> DailySettingsOut:
    row = await get_settings(session, account.id)
    if row is None:
        return DailySettingsOut(enabled=False, send_hour=9, last_sent_on=None)
    return DailySettingsOut(enabled=row.enabled, send_hour=row.send_hour, last_sent_on=row.last_sent_on)


@router.put("/daily", response_model=DailySettingsOut)
async def write_daily_settings(
    body: DailySettingsIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> DailySettingsOut:
    if body.enabled and not await is_subscriber(session, account.id):
        raise HTTPException(status_code=403, detail="daily horoscope is a subscriber feature")
    row = await upsert_settings(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        enabled=body.enabled,
        send_hour=body.send_hour,
    )
    return DailySettingsOut(enabled=row.enabled, send_hour=row.send_hour, last_sent_on=row.last_sent_on)


@router.get("/daily/horoscopes", response_model=list[DailyHoroscopeOut])
async def list_daily_horoscopes(
    limit: int = 30,
    offset: int = 0,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[DailyHoroscopeOut]:
    rows = await list_horoscopes(session, account_id=account.id, limit=limit, offset=offset)
    return [_daily_horoscope_out(row) for row in rows]
```

- [ ] **Step 5: Run tests + lint**

Run: `uv run pytest tests/test_api_daily.py -v` → PASS (6).
Run: `uv run ruff check src/quantuum/api/schemas.py src/quantuum/api/routes/me.py tests/test_api_daily.py` → `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/api/schemas.py src/quantuum/api/routes/me.py tests/test_api_daily.py
git commit -m "feat(daily): public API (GET/PUT /v1/me/daily + GET /v1/me/daily/horoscopes)"
```

---

## Task 8: i18n + DailyCb + bot handler

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (add `btn.daily` + `daily.*` keys)
- Modify: `src/quantuum/bot/ui/callbacks.py` (add `DailyCb`)
- Create: `src/quantuum/bot/handlers/daily.py`
- Test: `tests/test_daily_bot.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_daily_bot.py
from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import BuyCb, DailyCb
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, DailySubscription
from quantuum.domain.natal_profiles import upsert_natal_profile

from .conftest import build_translator


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


class FakeMessage:
    def __init__(self, text="", chat_id=1):
        self.text = text
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


class FakeCallback:
    def __init__(self, chat_id=1):
        self.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id), edit_text=AsyncMock())
        self.from_user = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


async def _seed(session, tenant_id, tg, *, subscriber=True, profile=True):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    if profile:
        await upsert_natal_profile(
            session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
            birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
            latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
        )
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    return acc


async def test_daily_command_subscriber_shows_status_off(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "100")

    msg = FakeMessage(text="/daily", chat_id=100)
    await daily.on_daily(msg, acc, i18n)
    assert msg.answer.await_args.args[0] == "Ежедневный гороскоп выключен."


async def test_daily_command_non_subscriber_upsell(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "101", subscriber=False)

    msg = FakeMessage(text="/daily", chat_id=101)
    await daily.on_daily(msg, acc, i18n)
    text = msg.answer.await_args.args[0]
    assert text == (
        "Ежедневный гороскоп доступен по подписке. "
        "Оформи подписку, чтобы получать его каждое утро:"
    )
    kb = msg.answer.await_args.kwargs["reply_markup"]
    assert BuyCb.unpack(kb.inline_keyboard[0][0].callback_data).action == "open"


async def test_daily_command_no_profile(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "102", profile=False)

    msg = FakeMessage(text="/daily", chat_id=102)
    await daily.on_daily(msg, acc, i18n)
    assert msg.answer.await_args.args[0] == "Сначала заполни натальный профиль (/profile)."


async def test_daily_toggle_enables(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "103")

    cb = FakeCallback(chat_id=103)
    await daily.on_daily_toggle(cb, acc, i18n)

    row = await session.get(DailySubscription, acc.id)
    assert row.enabled is True
    cb.message.edit_text.assert_awaited()
    assert cb.answer.await_args.args[0] == "Включил ежедневный гороскоп ✅"


async def test_daily_set_hour(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import daily

    _patch_sessionmaker(monkeypatch, daily, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await _seed(session, default_tenant.id, "104")

    cb = FakeCallback(chat_id=104)
    await daily.on_daily_set_hour(cb, DailyCb(action="set_hour", value=7), acc, i18n)

    row = await session.get(DailySubscription, acc.id)
    assert row.send_hour == 7
    assert (await session.execute(select(DailySubscription))).scalars().first().send_hour == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daily_bot.py -v`
Expected: FAIL — `ImportError: cannot import name 'DailyCb'` / `No module named 'quantuum.bot.handlers.daily'`.

- [ ] **Step 3: Add the callback factory**

In `src/quantuum/bot/ui/callbacks.py`, append:

```python
class DailyCb(CallbackData, prefix="daily"):
    action: str  # toggle | set_hour
    value: int = 0  # hour for set_hour
```

- [ ] **Step 4: Add i18n keys**

In `src/quantuum/i18n/seed_strings.py`, add `btn.daily` after the `btn.transits` entry:

```python
    "btn.daily": {
        "ru": "🔔 Ежедневный гороскоп",
        "en": "🔔 Daily horoscope",
    },
```

And add the `daily.*` block after the transit block (after `transit.failed`):

```python
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": {
        "ru": "🌟 Гороскоп на сегодня",
        "en": "🌟 Today's horoscope",
    },
    "daily.status_on": {
        "ru": "Ежедневный гороскоп включён. Время доставки: {hour}:00 (по твоему часовому поясу).",
        "en": "Daily horoscope is ON. Delivery time: {hour}:00 (your timezone).",
    },
    "daily.status_off": {
        "ru": "Ежедневный гороскоп выключен.",
        "en": "Daily horoscope is OFF.",
    },
    "daily.not_subscriber": {
        "ru": "Ежедневный гороскоп доступен по подписке. Оформи подписку, чтобы получать его каждое утро:",
        "en": "The daily horoscope is a subscriber feature. Subscribe to get it every morning:",
    },
    "daily.no_profile": {
        "ru": "Сначала заполни натальный профиль (/profile).",
        "en": "Fill in your natal profile first (/profile).",
    },
    "daily.enabled": {
        "ru": "Включил ежедневный гороскоп ✅",
        "en": "Daily horoscope enabled ✅",
    },
    "daily.disabled": {
        "ru": "Выключил ежедневный гороскоп.",
        "en": "Daily horoscope disabled.",
    },
    "daily.hour_set": {
        "ru": "Время доставки: {hour}:00 ✅",
        "en": "Delivery time: {hour}:00 ✅",
    },
    "daily.kb.turn_on": {
        "ru": "🔔 Включить",
        "en": "🔔 Turn on",
    },
    "daily.kb.turn_off": {
        "ru": "🔕 Выключить",
        "en": "🔕 Turn off",
    },
```

- [ ] **Step 5: Create the bot handler**

First READ `src/quantuum/bot/handlers/transits.py` and `src/quantuum/bot/handlers/buy.py` to confirm idioms (`get_sessionmaker()()`, `await i18n("key", hour=...)`, callback handlers receive `account`/`i18n` via middleware, `_buy_offer_kb` from `quantuum.bot.handlers.generate`). Create `src/quantuum/bot/handlers/daily.py`:

```python
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.callbacks import DailyCb
from quantuum.db.models import Account, DailySubscription
from quantuum.db.session import get_sessionmaker
from quantuum.domain.daily import get_settings, is_subscriber, upsert_settings
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.i18n import Translator

router = Router()


async def _daily_view(
    i18n: Translator, settings: DailySubscription | None
) -> tuple[str, InlineKeyboardMarkup]:
    enabled = settings.enabled if settings else False
    hour = settings.send_hour if settings else 9
    text = await i18n("daily.status_on", hour=hour) if enabled else await i18n("daily.status_off")
    b = InlineKeyboardBuilder()
    toggle_key = "daily.kb.turn_off" if enabled else "daily.kb.turn_on"
    b.button(text=await i18n(toggle_key), callback_data=DailyCb(action="toggle"))
    for h in range(24):
        label = f"·{h}·" if h == hour else str(h)
        b.button(text=label, callback_data=DailyCb(action="set_hour", value=h))
    b.adjust(1, 6, 6, 6, 6)
    return text, b.as_markup()


async def run_daily_settings(message: Message, account: Account, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if not await is_subscriber(session, account.id):
            await message.answer(
                await i18n("daily.not_subscriber"), reply_markup=await _buy_offer_kb(i18n)
            )
            return
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message.answer(await i18n("daily.no_profile"))
            return
        settings = await get_settings(session, account.id)
    text, kb = await _daily_view(i18n, settings)
    await message.answer(text, reply_markup=kb)


@router.message(Command("daily"))
async def on_daily(message: Message, account: Account, i18n: Translator) -> None:
    await run_daily_settings(message, account, i18n)


@router.callback_query(DailyCb.filter(F.action == "toggle"))
async def on_daily_toggle(query: CallbackQuery, account: Account, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if not await is_subscriber(session, account.id):
            await query.answer(await i18n("daily.not_subscriber"), show_alert=True)
            return
        current = await get_settings(session, account.id)
        new_enabled = not (current.enabled if current else False)
        hour = current.send_hour if current else 9
        settings = await upsert_settings(
            session, tenant_id=account.tenant_id, account_id=account.id,
            enabled=new_enabled, send_hour=hour,
        )
    text, kb = await _daily_view(i18n, settings)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer(await i18n("daily.enabled" if new_enabled else "daily.disabled"))


@router.callback_query(DailyCb.filter(F.action == "set_hour"))
async def on_daily_set_hour(
    query: CallbackQuery, callback_data: DailyCb, account: Account, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_subscriber(session, account.id):
            await query.answer(await i18n("daily.not_subscriber"), show_alert=True)
            return
        current = await get_settings(session, account.id)
        enabled = current.enabled if current else False
        settings = await upsert_settings(
            session, tenant_id=account.tenant_id, account_id=account.id,
            enabled=enabled, send_hour=callback_data.value,
        )
    text, kb = await _daily_view(i18n, settings)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer(await i18n("daily.hour_set", hour=callback_data.value))
```

- [ ] **Step 6: Run tests + lint**

Run: `uv run pytest tests/test_daily_bot.py -v` → PASS (5).
Run: `uv run ruff check src/quantuum/bot/handlers/daily.py src/quantuum/bot/ui/callbacks.py src/quantuum/i18n/seed_strings.py tests/test_daily_bot.py` → `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/handlers/daily.py src/quantuum/bot/ui/callbacks.py src/quantuum/i18n/seed_strings.py tests/test_daily_bot.py
git commit -m "feat(daily): /daily bot command + settings view + toggle/hour callbacks + i18n"
```

---

## Task 9: Menu / keyboards / app wiring + keyboard test updates

**Files:**
- Modify: `src/quantuum/bot/ui/text.py` (`MENU_BUTTON_KEYS`)
- Modify: `src/quantuum/bot/ui/keyboards.py` (`main_menu_kb`)
- Modify: `src/quantuum/bot/handlers/menu.py` (route the daily button)
- Modify: `src/quantuum/bot/app.py` (include `daily.router`)
- Test: modify `tests/test_ui_keyboards.py` and `tests/test_bot_start_menu_profile.py`

- [ ] **Step 1: Update the keyboard tests (failing first)**

In `tests/test_ui_keyboards.py`, update the two menu assertions to expect 7 buttons (READ the file to find them; they currently assert 6). Replace the expected sets with:

```python
    assert set(_reply_texts(kb)) == {
        "🔮 Разбор", "❓ Спросить астролога", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь",
    }
```

and for the English (`lang="en"`) test:

```python
    assert set(_reply_texts(kb)) == {
        "🔮 Reading", "❓ Ask the astrologer", "🌌 Transits", "🔔 Daily horoscope",
        "👤 Profile", "📜 History", "ℹ️ Help",
    }
```

In `tests/test_bot_start_menu_profile.py`, update BOTH menu assertions (the `/start` test uses `_reply_texts(menu_markup)` and the help test uses `_reply_texts(markup)`) to the same RU 7-button set:

```python
    assert set(_reply_texts(menu_markup)) == {
        "🔮 Разбор", "❓ Спросить астролога", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь"
    }
```

```python
    assert set(_reply_texts(markup)) == {
        "🔮 Разбор", "❓ Спросить астролога", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь"
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui_keyboards.py tests/test_bot_start_menu_profile.py -v`
Expected: FAIL (menu still has 6 buttons, "🔔 Ежедневный гороскоп" missing).

- [ ] **Step 3: Wire the menu key**

In `src/quantuum/bot/ui/text.py`, update `MENU_BUTTON_KEYS` to insert `"btn.daily"` after `"btn.transits"`:

```python
MENU_BUTTON_KEYS = ("btn.generate", "btn.ask", "btn.transits", "btn.daily", "btn.profile", "btn.history", "btn.help")
```

- [ ] **Step 4: Wire the keyboard**

In `src/quantuum/bot/ui/keyboards.py`, update `main_menu_kb` to add the daily button after the transits button and re-balance to 7 buttons:

```python
async def main_menu_kb(i18n: Translator) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=await i18n("btn.generate"))
    b.button(text=await i18n("btn.ask"))
    b.button(text=await i18n("btn.transits"))
    b.button(text=await i18n("btn.daily"))
    b.button(text=await i18n("btn.profile"))
    b.button(text=await i18n("btn.history"))
    b.button(text=await i18n("btn.help"))
    b.adjust(2, 2, 2, 1)
    return b.as_markup(resize_keyboard=True, is_persistent=True)
```

- [ ] **Step 5: Route the menu button**

In `src/quantuum/bot/handlers/menu.py`:
- Add the import next to the other handler imports:
  ```python
  from quantuum.bot.handlers.daily import run_daily_settings
  ```
- Add the label set next to the others (after `_TRANSITS_LABELS`):
  ```python
  _DAILY_LABELS = text.menu_button_labels("btn.daily")
  ```
- Add the handler next to `on_transits_btn`:
  ```python
  @router.message(F.text.in_(_DAILY_LABELS))
  async def on_daily_btn(message: Message, account: Account, i18n: Translator) -> None:
      await run_daily_settings(message, account, i18n)
  ```

- [ ] **Step 6: Include the router**

In `src/quantuum/bot/app.py`:
- Add `daily` to the `from quantuum.bot.handlers import (...)` tuple.
- Include the router right after `dp.include_router(transits.router)`:
  ```python
      dp.include_router(daily.router)
  ```

- [ ] **Step 7: Run tests + lint**

Run: `uv run pytest tests/test_ui_keyboards.py tests/test_bot_start_menu_profile.py -v` → PASS.
Run: `uv run ruff check src/quantuum/bot/ tests/test_ui_keyboards.py tests/test_bot_start_menu_profile.py` → `All checks passed!`.

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/bot/ui/text.py src/quantuum/bot/ui/keyboards.py \
        src/quantuum/bot/handlers/menu.py src/quantuum/bot/app.py \
        tests/test_ui_keyboards.py tests/test_bot_start_menu_profile.py
git commit -m "feat(daily): main-menu button + router wiring (7-button menu)"
```

---

## Stage completion

- [ ] Full suite: `uv run pytest -q` (expect all green; the transit-engine + daily compute tests add a few seconds). If the shared test DB shows a contention ERROR on an unrelated test, re-run that test in isolation (see the test-DB memory).
- [ ] Lint: `uv run ruff check .` → "All checks passed!".
- [ ] Migrations: `uv run alembic heads` → single head `d9e0f1a2b3c4`; `uv run alembic upgrade head --sql > /dev/null && echo OK`.
- [ ] Final holistic review of `feat/daily-horoscope` (dispatch a final code reviewer over the whole branch), then use `superpowers:finishing-a-development-branch`.

## Self-review checklist (spec coverage)

- §2 audience/billing: subscriber-only (`is_subscriber`), free (no consume_quota anywhere). ✓ (Tasks 3, 5, 7, 8)
- §3 data model: `daily_subscriptions` + `daily_horoscopes` + unique `(account_id, local_date)` + migration from head `c8d9e0f1a2b3`. ✓ (Task 1)
- §4 engine reuse + short narration: `compute_transits(window_days=7)` + `render_daily_md(ahead_days=3)` + `daily_horoscope` LLM + prompt. ✓ (Tasks 2, 4, 5)
- §5 scheduling/timezone/idempotency: `daily_dispatch` hourly cron → `due_daily_account_ids` (ZoneInfo local hour + last_sent_on) → enqueue `daily_generate`; claim-row + `last_sent_on`. ✓ (Tasks 3, 5, 6)
- §6 surfaces: bot `/daily` + menu button + toggle/hour; API GET/PUT/horoscopes. ✓ (Tasks 7, 8, 9)
- §7 i18n: `btn.daily` + `daily.*` (ru+en). ✓ (Task 8)
- §8 error handling: not-subscriber/no-profile/already-sent skip; LLM failure → failed + last_sent_on set, no delivery; delivery best-effort outside session. ✓ (Task 5)
- §9 testing: models, engine, domain (incl. due-selection), llm, task (5 paths), dispatch, api, bot, keyboards/menu, migration single-head. ✓
- §10 migration: `d9e0f1a2b3c4` from `c8d9e0f1a2b3`, single head. ✓ (Task 1)
- §13 decisions: tenant-bot delivery (not ctx["bot"]); failed skips day; per-user local hour default 9. ✓ (Tasks 5, 8)
