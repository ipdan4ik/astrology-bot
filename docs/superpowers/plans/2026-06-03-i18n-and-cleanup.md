# i18n & Correctness Cleanup (Workstream G) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a crash-on-missing-payment, make payout calculation idempotent, lock down `set_*_status` keyword injection, localize reading status in history without raw `.format()` crashes, and force-resync renamed i18n keys onto already-seeded databases.

**Architecture:** Five independent fixes: (1) `mark_payment_paid` None-guard; (2) `calculate_payout` reuses an existing period payout + a unique constraint; (3) `set_*_status` setters allowlist their `**fields` keys; (4) `history._render_readings` renders status via `status_label` and `safe_format`; (5) a bootstrap `force_update_strings` helper + a one-time migration that updates renamed keys (the seeder is insert-only and won't update them).

**Tech Stack:** SQLAlchemy async, Alembic, aiogram handlers, Pydantic, pytest. Current alembic head: `b2d3f4a5c607`.

**Test command:** `uv run pytest <path> -v`. asyncio auto mode (no decorator); fixtures `session`, `default_tenant`, `build_translator`. For each task READ the named existing test file first and mirror its setup. Do NOT weaken assertions.

---

### Task 1: `mark_payment_paid` None guard (crash fix)

**Files:**
- Modify: `src/quantuum/domain/billing.py:50-61`
- Test: `tests/test_billing_payments.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_mark_payment_paid_missing_payment_raises_notfound(session):
    import pytest
    from quantuum.common.exceptions import NotFoundError  # confirm import path
    from quantuum.domain.billing import mark_payment_paid
    with pytest.raises(NotFoundError):
        await mark_payment_paid(session, payment_id=999999, external_id="x")
```

NOTE: confirm the project's not-found exception (grep `class NotFoundError` / how other domain fns signal missing rows). If the codebase has no such exception, raise `ValueError` instead and assert that.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_payments.py -k missing_payment_raises -v`
Expected: FAIL — currently `AttributeError: 'NoneType' object has no attribute 'status'`.

- [ ] **Step 3: Implement**

In `mark_payment_paid`, after fetching, guard None:

```python
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError(f"payment {payment_id} not found")
    if payment.status == "paid":
        return payment
```

Add the import at the top of `billing.py` if needed: `from quantuum.common.exceptions import NotFoundError`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing_payments.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/billing.py tests/test_billing_payments.py
git commit -m "fix(billing): mark_payment_paid guards missing payment"
```

---

### Task 2: Idempotent payout calculation

**Files:**
- Modify: `src/quantuum/domain/payouts.py:23` (`calculate_payout` — reuse existing period payout)
- Modify: `src/quantuum/db/models.py:419` (`Payout` — add unique constraint)
- Create: `alembic/versions/c3e4f5a6b708_payout_period_unique.py`
- Test: `tests/test_payouts_domain.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_calculate_payout_is_idempotent(session, default_tenant):
    from datetime import datetime, timezone
    from sqlalchemy import select, func
    from quantuum.db.models import Payout
    from quantuum.domain.payouts import calculate_payout
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, tzinfo=timezone.utc)
    p1 = await calculate_payout(
        session, tenant_id=default_tenant.id, period_start=start, period_end=end,
        fee_pct=10, calculated_by_account_id=None,
    )
    p2 = await calculate_payout(
        session, tenant_id=default_tenant.id, period_start=start, period_end=end,
        fee_pct=10, calculated_by_account_id=None,
    )
    assert p2.id == p1.id  # reused, not duplicated
    n = (await session.execute(
        select(func.count()).select_from(Payout).where(Payout.tenant_id == default_tenant.id)
    )).scalar()
    assert n == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payouts_domain.py -k is_idempotent -v`
Expected: FAIL — two rows created (`p2.id != p1.id`, `n == 2`).

- [ ] **Step 3: Implement the reuse check**

In `src/quantuum/domain/payouts.py`, at the start of `calculate_payout` (before computing/inserting), reuse an existing period payout:

```python
    existing = await find_payout_for_period(
        session, tenant_id=tenant_id, period_start=period_start, period_end=period_end
    )
    if existing is not None:
        return existing
```

(`find_payout_for_period` already exists in this module.)

- [ ] **Step 4: Add the unique constraint to the model**

In `src/quantuum/db/models.py`, in the `Payout` class, add `__table_args__` (import `UniqueConstraint` from sqlalchemy if not already imported):

```python
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "period_start", "period_end",
            name="uq_payout_tenant_period",
        ),
    )
```

- [ ] **Step 5: Write the migration**

Confirm `c3e4f5a6b708` is unused. Create `alembic/versions/c3e4f5a6b708_payout_period_unique.py`:

```python
"""payouts unique (tenant_id, period_start, period_end)

Revision ID: c3e4f5a6b708
Revises: b2d3f4a5c607
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3e4f5a6b708"
down_revision: Union[str, Sequence[str], None] = "b2d3f4a5c607"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_payout_tenant_period", "payouts",
        ["tenant_id", "period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_payout_tenant_period", "payouts", type_="unique")
```

- [ ] **Step 6: Run test + confirm single head**

Run: `uv run pytest tests/test_payouts_domain.py -v` → PASS
Run: `uv run alembic heads` → single head `c3e4f5a6b708`.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/domain/payouts.py src/quantuum/db/models.py alembic/versions/c3e4f5a6b708_payout_period_unique.py tests/test_payouts_domain.py
git commit -m "fix(payouts): idempotent calculate_payout + period unique constraint"
```

---

### Task 3: Allowlist `set_*_status` keyword fields

**Files:**
- Modify: `src/quantuum/domain/readings.py:35` (`set_reading_status`), `src/quantuum/domain/qa.py:53` (`set_qa_status`), `src/quantuum/domain/transits.py:54` (`set_transit_status`), `src/quantuum/domain/daily.py:75` (`set_horoscope_status`)
- Test: `tests/test_set_status_allowlist.py` (create)

**Pattern:** each setter does `for key, value in fields.items(): setattr(row, key, value)` — arbitrary attribute write. Add a per-setter allowlist (the model's content columns) and raise `ValueError` on an unknown key.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_set_status_allowlist.py
import pytest


async def test_set_reading_status_rejects_unknown_field(session, default_tenant):
    from quantuum.domain.readings import create_reading, set_reading_status
    from quantuum.db.models import NatalProfile
    # minimal reading (reuse a helper if the readings test file has one)
    prof = NatalProfile(tenant_id=default_tenant.id, account_id=1, full_name="x",
                        birth_date="1990-01-01", birth_time="12:00:00",
                        birth_place="y", latitude=0, longitude=0, timezone="UTC")
    session.add(prof); await session.flush()
    reading = await create_reading(
        session, tenant_id=default_tenant.id, account_id=1,
        natal_profile_id=prof.id, kind="tarot", lang="en",
    )
    with pytest.raises(ValueError):
        await set_reading_status(session, reading.id, "done", is_superadmin=True)
```

NOTE: adapt the reading/profile construction to the real model columns + the readings test file's existing helper (grep `create_reading` usage in tests). The contract: passing a field NOT in the allowlist raises `ValueError`; a legitimate field (e.g. `llm_md="..."`) still works (add a positive assertion too).

Add an analogous positive test:
```python
async def test_set_reading_status_allows_known_field(session, default_tenant):
    # ... same setup ...
    await set_reading_status(session, reading.id, "done", llm_md="result")
    from quantuum.domain.readings import get_reading
    r = await get_reading(session, reading.id)
    assert r.llm_md == "result" and r.status == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_set_status_allowlist.py -v`
Expected: the reject test FAILS (no ValueError — `is_superadmin` would be silently setattr'd or AttributeError, not ValueError).

- [ ] **Step 3: Implement the allowlists**

In each setter, define a module-level allowlist and validate. Example for `readings.py`:

```python
_STATUS_FIELDS = frozenset({
    "calc_md", "llm_md", "llm_provider", "llm_model",
    "llm_tokens_in", "llm_tokens_out", "error", "draw_jsonb",
})


async def set_reading_status(session, reading_id: int, status: str, **fields) -> None:
    unknown = set(fields) - _STATUS_FIELDS
    if unknown:
        raise ValueError(f"set_reading_status: disallowed fields {sorted(unknown)}")
    reading = await get_reading(session, reading_id)
    reading.status = status
    for key, value in fields.items():
        setattr(reading, key, value)
    ...
```

Apply the same pattern with the correct allowlist per model:
- `qa.py` `_STATUS_FIELDS = {"answer_md", "lang", "error", "llm_provider", "llm_model", "llm_tokens_in", "llm_tokens_out"}`
- `transits.py` `_STATUS_FIELDS = {"transit_md", "report_md", "lang", "error", "llm_provider", "llm_model", "llm_tokens_in", "llm_tokens_out"}`
- `daily.py` `_STATUS_FIELDS = {"transit_md", "horoscope_md", "lang", "error", "llm_provider", "llm_model", "llm_tokens_in", "llm_tokens_out"}`

VERIFY each allowlist against the real model columns (grep `class Reading`/`class QaAnswer`/`class TransitReport`/`class DailyHoroscope`) — include every content column the workers actually set, or you'll break worker writes. Check the worker call sites (`grep -rn "set_reading_status\|set_qa_status\|set_transit_status\|set_horoscope_status" src/`) and ensure every field they pass is in the allowlist.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_set_status_allowlist.py -v`
Expected: PASS

- [ ] **Step 5: Run the worker/domain suites that exercise these setters**

Run: `uv run pytest tests/ -k "reading or qa or transit or horoscope or daily or task" -q`
Expected: all PASS (no legitimate worker write rejected).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/readings.py src/quantuum/domain/qa.py src/quantuum/domain/transits.py src/quantuum/domain/daily.py tests/test_set_status_allowlist.py
git commit -m "fix(domain): allowlist set_*_status keyword fields"
```

---

### Task 4: Localize reading status in history (no raw .format())

**Files:**
- Modify: `src/quantuum/bot/handlers/history.py:31-50` (`_render_readings`)
- Test: `tests/test_history_screen.py`

- [ ] **Step 1: Write the failing test**

Mirror `tests/test_history_screen.py`'s setup (it builds an account + readings and calls the history render). Add a test that a reading with status `"pending"` renders the LOCALIZED status label (not the raw word) and that a `kind` with no i18n key falls back without crashing.

```python
async def test_history_readings_localizes_status(session, default_tenant, ...):
    # seed a reading with status="pending", kind="tarot"
    # build a real translator (build_translator) so status.pending resolves
    # call the readings-history render (use the file's actual entrypoint/target)
    answers = [...captured target.answer text...]
    # the localized label for status.pending (e.g. RU "в очереди") appears,
    # and the raw "pending" does NOT appear as the status token
    assert any(<localized status.pending> in a for a in answers)
```

NOTE: read the file to see how it builds `target`, `i18n`, and captures `answer` calls; mirror it. Resolve the expected localized value via `await i18n("status.pending")` in the test rather than hardcoding.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_history_screen.py -k localizes_status -v`
Expected: FAIL — current code passes raw `r.status` into the row.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/history.py`, import the helpers:

```python
from quantuum.bot.ui.text import render_detail, render_history_label, status_label
from quantuum.i18n.resolver import safe_format
```

In `_render_readings`, replace the row construction:

```python
    for r in readings:
        kind_label = await i18n(f"readings.kind.{r.kind}", default=r.kind)
        template = await i18n("history.reading_row")
        row_text = safe_format(template, {
            "kind": kind_label,
            "status": await status_label(i18n, r.status),
            "date": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "—",
        })
        ...
```

(`safe_format` leaves unknown placeholders intact instead of raising `KeyError`/`IndexError` on a stray brace; `status_label` localizes via `status.{status}` with raw fallback; the `default=r.kind` keeps an unknown kind from rendering an empty/raw key.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_history_screen.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/history.py tests/test_history_screen.py
git commit -m "fix(history): localize reading status, drop raw str.format()"
```

---

### Task 5: Force-resync renamed i18n keys

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (add a `RESYNC_KEYS` list)
- Modify: `src/quantuum/db/bootstrap.py` (add `force_update_strings`)
- Create: `alembic/versions/d4f5a6b7c809_resync_renamed_strings.py`
- Test: `tests/test_bootstrap_platform.py` (or a new `tests/test_force_update_strings.py`)

**Context:** `ensure_base_strings` only INSERTs, so when a key's text was renamed in `BASE_STRINGS` (Blueprint rename, `help.text`, `btn.generate`) an already-seeded DB keeps the stale text. We add a helper that force-UPDATEs a curated key set from `BASE_STRINGS`, and a one-time migration. (Cache invalidation: the helper calls `invalidate_i18n_all()`; the migration only updates the DB — caches rebuild on the standard post-deploy app restart.)

- [ ] **Step 1: Define the resync key set**

In `src/quantuum/i18n/seed_strings.py`, after `BASE_STRINGS`, add:

```python
# Keys whose text was renamed AFTER initial seed; ensure_base_strings is
# insert-only, so these must be force-updated on already-seeded DBs.
RESYNC_KEYS: list[str] = [
    "btn.generate",
    "help.text",
]
```

Then add the Blueprint-renamed keys: grep `BASE_STRINGS` for entries whose text contains `"Blueprint"` and add their dotted keys to `RESYNC_KEYS` (e.g. the blueprint detail/title/empty-state keys). Include every key you changed in the rename commits — when unsure, include it (force-updating a key to its current BASE_STRINGS value is harmless; it only matters for stale rows).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_force_update_strings.py
from quantuum.db.bootstrap import force_update_strings
from quantuum.db.models import PlatformString
from quantuum.i18n.seed_strings import BASE_STRINGS


async def test_force_update_strings_overwrites_stale(session):
    # seed a STALE value for an existing key
    session.add(PlatformString(key="btn.generate", lang="en", text="OLD VALUE"))
    await session.commit()

    await force_update_strings(session, ["btn.generate"])

    row = await session.get(PlatformString, ("btn.generate", "en"))
    await session.refresh(row)
    assert row.text == BASE_STRINGS["btn.generate"]["en"]  # updated to current
    assert row.text != "OLD VALUE"
```

NOTE: confirm `PlatformString`'s composite PK access via `session.get(PlatformString, (key, lang))`. If `force_update_strings` calls `invalidate_i18n_all` (which hits Redis), the test harness's Redis is available (conftest flushes it), so the call is safe in tests.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_force_update_strings.py -v`
Expected: FAIL — `force_update_strings` doesn't exist.

- [ ] **Step 4: Implement the helper**

In `src/quantuum/db/bootstrap.py`, add:

```python
async def force_update_strings(session, keys) -> None:
    """Force platform_strings text for *keys* to match BASE_STRINGS (UPDATE existing,
    INSERT missing), then invalidate i18n caches. Unlike ensure_base_strings this
    OVERWRITES existing rows — use only for keys renamed after the initial seed."""
    from quantuum.i18n.cache import invalidate_i18n_all
    from quantuum.i18n.seed_strings import BASE_STRINGS

    changed = False
    for key in keys:
        for lang, text in BASE_STRINGS.get(key, {}).items():
            row = await session.get(PlatformString, (key, lang))
            if row is None:
                session.add(PlatformString(key=key, lang=lang, text=text))
                changed = True
            elif row.text != text:
                row.text = text
                session.add(row)
                changed = True
    if changed:
        await session.commit()
    await invalidate_i18n_all()
```

- [ ] **Step 5: Write the migration**

Confirm `d4f5a6b7c809` is unused. Create `alembic/versions/d4f5a6b7c809_resync_renamed_strings.py` — a data migration that updates the renamed keys from `BASE_STRINGS` (DB-only; caches rebuild on restart):

```python
"""resync renamed i18n keys onto seeded DBs

Revision ID: d4f5a6b7c809
Revises: c3e4f5a6b708
Create Date: 2026-06-04 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f5a6b7c809"
down_revision: Union[str, Sequence[str], None] = "c3e4f5a6b708"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from quantuum.i18n.seed_strings import BASE_STRINGS, RESYNC_KEYS

    conn = op.get_bind()
    for key in RESYNC_KEYS:
        for lang, text in BASE_STRINGS.get(key, {}).items():
            conn.execute(
                sa.text(
                    "UPDATE platform_strings SET text = :t WHERE key = :k AND lang = :l"
                ),
                {"t": text, "k": key, "l": lang},
            )


def downgrade() -> None:
    # Text-only data migration; no-op down (old text is not retained).
    pass
```

- [ ] **Step 6: Run test + confirm single head**

Run: `uv run pytest tests/test_force_update_strings.py -v` → PASS
Run: `uv run alembic heads` → single head `d4f5a6b7c809`.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/db/bootstrap.py alembic/versions/d4f5a6b7c809_resync_renamed_strings.py tests/test_force_update_strings.py
git commit -m "fix(i18n): force-resync renamed keys onto already-seeded DBs"
```

---

### Task 6: Stage regression — full suite

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (prior baseline 2059 passed + this plan's new tests). Confirm `uv run alembic heads` is a single head `d4f5a6b7c809`.

- [ ] **Step 2: If anything fails**

The most likely regression is a worker/test that passed a field to a `set_*_status` setter that you omitted from its allowlist → now raises `ValueError`. Fix by ADDING the legitimate field to that setter's allowlist (it's a real content column), not by removing the allowlist. Re-grep the worker call sites to be sure every field they pass is permitted. Do NOT weaken assertions.

- [ ] **Step 3: Commit** any allowlist additions with a clear message.

---

## Notes / scope

- The i18n resync migration is DB-only; i18n caches (Redis) rebuild on the post-deploy app restart. The `force_update_strings` helper additionally invalidates caches and can be invoked manually if a hot resync is needed.
- After this plan, update the `audit-fix-sweep-progress` memory: G DONE. Only Workstream F (UX) remains.
