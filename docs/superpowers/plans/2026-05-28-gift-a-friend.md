# SP5 — Gift-a-Friend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a customer to gift `package_credits` to another Telegram user via a `t.me/<bot>?start=<code>` deep link. Sender is debited at creation; unclaimed gifts auto-refund on expiry via a lazy sweep when the sender next opens `/gift`.

**Architecture:** Re-uses SP4 `start_tokens` with `kind="gift"`. Drop the SP4 global UNIQUE on `start_token_uses(account_id)` so each kind handler enforces its own uniqueness. New domain module `gifts.py`, new bot handler `gift.py`, owner console gets a `Gifts` submenu mirroring SP3 Branding / SP4 Referrals.

**Tech Stack:** Python 3.13 (PEP 604 unions), SQLModel + Alembic on PostgreSQL, aiogram 3 (CallbackData + FSM), structlog, pytest-asyncio (asyncio_mode=auto). Standing constraints: work on `main`, ruff-clean source, no emojis, TDD red→green→commit per task, per-task targeted tests during execution, full suite + ruff only at stage end.

**Spec:** `docs/superpowers/specs/2026-05-28-gift-a-friend-design.md`

---

## File map

**Created**

- `alembic/versions/f2a3b4c5d6e7_drop_start_token_uses_account_unique.py` — migration
- `src/quantuum/domain/gifts.py` — domain layer
- `src/quantuum/bot/handlers/gift.py` — `/gift` + FSM + menu button
- `tests/test_gift_domain.py`
- `tests/test_gift_handler.py`
- `tests/test_owner_gifts.py`
- `tests/test_gift_i18n.py`
- `tests/test_start_token_uses_no_unique.py` — schema smoke test for T1

**Modified**

- `src/quantuum/db/models.py:529-533` — drop `UniqueConstraint(...)` from `StartTokenUse.__table_args__`
- `src/quantuum/bot/handlers/start_tokens.py` — add `handle_gift_token`, register in `_HANDLERS`, change `dispatch_start_token` to return `GiftClaimResult | None`
- `src/quantuum/bot/handlers/start.py` — surface `gift.received` when dispatch returns a `GiftClaimResult`
- `src/quantuum/bot/handlers/owner_console.py` — `OwnerGifts` FSM, Gifts submenu handlers, `Gifts` button on `/manage`
- `src/quantuum/bot/ui/callbacks.py` — `OwnerGiftsCb(CallbackData, prefix="ogft")`
- `src/quantuum/bot/ui/text.py` — extend `MENU_BUTTON_KEYS` with `btn.gift`
- `src/quantuum/bot/ui/keyboards.py` — add `btn.gift` to `main_menu_kb` gated on the `gifts` flag
- `src/quantuum/bot/app.py` — include `gift.router`
- `src/quantuum/domain/tenant_features.py` — append `"gifts"` to `FEATURE_KEYS`
- `src/quantuum/i18n/seed_strings.py` — 30 new keys (`ru` + `en`)
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — same 30 keys per locale
- `tests/test_tenant_features_domain.py` — bump 13→14 inventory assertions, add `"gifts"` to the canonical set

---

## Task 1 — Drop global UNIQUE on `start_token_uses`

**Files:**
- Create: `alembic/versions/f2a3b4c5d6e7_drop_start_token_uses_account_unique.py`
- Modify: `src/quantuum/db/models.py:529-533`
- Test: `tests/test_start_token_uses_no_unique.py`

**Context:** SP4 added `UniqueConstraint("account_id", name="uq_start_token_uses_account_id")`. For SP5, multiple users can claim multiple kinds of start_token (a referral attribution today, a gift tomorrow). Per-kind handlers enforce their own rules; the DB constraint goes away. The SP4 referral handler already does its own pre-flight SELECT (`src/quantuum/bot/handlers/start_tokens.py:71-75`), so behaviour is unchanged for referrals.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_start_token_uses_no_unique.py
from sqlalchemy import inspect

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import StartToken, StartTokenUse, Tenant


async def test_start_token_uses_has_no_unique_on_account(session):
    """After SP5 T1, two rows with the same account_id can coexist."""
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )

    session.add(StartToken(code="AAA00001", kind="referral", tenant_id=t.id,
                           owner_account_id=acc.id, status="active"))
    session.add(StartToken(code="BBB00002", kind="gift", tenant_id=t.id,
                           owner_account_id=acc.id, status="active"))
    await session.flush()
    session.add(StartTokenUse(token_code="AAA00001", account_id=acc.id))
    session.add(StartTokenUse(token_code="BBB00002", account_id=acc.id))
    await session.flush()  # must NOT raise IntegrityError


def test_start_token_uses_table_has_no_unique_index(sync_engine):
    """Static check: table has no unique constraint involving account_id alone."""
    insp = inspect(sync_engine)
    uniques = insp.get_unique_constraints("start_token_uses")
    for uc in uniques:
        assert uc["column_names"] != ["account_id"], (
            f"start_token_uses still has a UNIQUE(account_id): {uc}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_start_token_uses_no_unique.py -v
```

Expected: FAIL with `IntegrityError` / `UniqueViolationError` on the duplicate insert, and the static check finds the existing `uq_start_token_uses_account_id`.

- [ ] **Step 3: Write the migration**

```python
# alembic/versions/f2a3b4c5d6e7_drop_start_token_uses_account_unique.py
"""drop start_token_uses unique account_id

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-28 00:00:00.000000
"""
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_start_token_uses_account_id",
        "start_token_uses",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_start_token_uses_account_id",
        "start_token_uses",
        ["account_id"],
    )
```

Confirm the `down_revision` matches SP4's final start-tokens migration before committing — run `ls alembic/versions/ | sort` and verify `e1f2a3b4c5d6_start_tokens.py` is the chain head.

- [ ] **Step 4: Update the model**

Open `src/quantuum/db/models.py:529-533`. The current shape is:

```python
class StartTokenUse(SQLModel, table=True):
    __tablename__ = "start_token_uses"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_start_token_uses_account_id"),
    )
```

Remove `__table_args__` entirely (the only constraint in it is the one being dropped):

```python
class StartTokenUse(SQLModel, table=True):
    __tablename__ = "start_token_uses"

    id: int | None = Field(default=None, primary_key=True)
    ...
```

If `UniqueConstraint` is now unused, drop it from the import line at the top of the file as well — `ruff check` will catch this.

- [ ] **Step 5: Run test to verify it passes**

```
uv run pytest tests/test_start_token_uses_no_unique.py -v
```

Expected: PASS on both tests. The test fixtures must rebuild schema (per-session fixture in `conftest.py` already does this since the model changed).

- [ ] **Step 6: Re-run SP4 referral attribution tests to confirm no regression**

```
uv run pytest tests/test_start_token_dispatcher.py tests/test_referral_domain.py -v
```

Expected: all pass — the SP4 handler's pre-flight SELECT covers the "already attributed" guard without the DB constraint.

- [ ] **Step 7: Commit**

```
git add alembic/versions/f2a3b4c5d6e7_drop_start_token_uses_account_unique.py \
        src/quantuum/db/models.py \
        tests/test_start_token_uses_no_unique.py
git commit -m "feat(sp5-t1): drop start_token_uses(account_id) UNIQUE"
```

---

## Task 2 — Domain layer `gifts.py`

**Files:**
- Create: `src/quantuum/domain/gifts.py`
- Create: `tests/test_gift_domain.py`

**Context:** Mirrors `src/quantuum/domain/referrals.py` patterns. `record_audit` lives at `quantuum.domain.audit.record_audit` and takes `(session, *, tenant_id, actor_account_id, action, entity_type, entity_id, payload)`. `adjust_package_credits` is at `quantuum.domain.accounts.adjust_package_credits(session, account_id, delta)`. `find_or_create_account_by_tg(session, *, tenant_id: int, tg_user_id: str) -> Account` lives at `quantuum.auth.identity`. `AccountBalance` PK is `account_id`. Use `quantuum.common.datetime.utcnow` for "now". `TenantConfig` composite PK is `(tenant_id, key)`; SP4 used `session.get(TenantConfig, (tenant_id, key))`.

- [ ] **Step 1: Write the failing test file (skeleton — full code follows in this task)**

```python
# tests/test_gift_domain.py
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AuditLog,
    StartToken,
    StartTokenUse,
    Tenant,
    TenantConfig,
)
from quantuum.domain.gifts import (
    DEFAULT_EXPIRY_DAYS,
    GIFT_EXPIRY_CONFIG_KEY,
    GIFT_KIND,
    MAX_EXPIRY_DAYS,
    MAX_GIFT_AMOUNT,
    MIN_EXPIRY_DAYS,
    InsufficientCreditsError,
    create_gift,
    get_expiry_days,
    list_recent_gifts,
    reset_expiry_days,
    set_expiry_days,
    sweep_expired_gifts,
)


async def _tenant(session: AsyncSession) -> Tenant:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    return t


async def _account_with_credits(session, tenant_id, tg, credits):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.flush()
    return acc


async def test_create_gift_happy_path(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 50)

    token = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=15
    )

    assert token.kind == GIFT_KIND
    assert token.owner_account_id == sender.id
    assert token.tenant_id == t.id
    assert token.payload == {"amount": 15}
    assert token.max_uses == 1
    assert token.status == "active"
    assert token.expires_at is not None and token.expires_at > utcnow()

    bal = await session.get(AccountBalance, sender.id)
    assert bal.package_credits == 35

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "gift.created"))
    ).scalars().one()
    assert audit.payload_jsonb["amount"] == 15
    assert audit.payload_jsonb["code"] == token.code


async def test_create_gift_uses_tenant_expiry(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 50)
    await set_expiry_days(
        session, tenant_id=t.id, days=7, by_account_id=sender.id
    )
    await session.flush()

    token = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=5
    )
    # ~7d (slight slack for clock drift between fixture and code)
    delta = (token.expires_at - utcnow()).total_seconds()
    assert 7 * 86400 - 60 < delta < 7 * 86400 + 60


@pytest.mark.parametrize("amount", [0, -1, MAX_GIFT_AMOUNT + 1, 5000])
async def test_create_gift_invalid_amount_raises(session: AsyncSession, amount):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 5000)
    with pytest.raises(ValueError):
        await create_gift(
            session, sender_account_id=sender.id, tenant_id=t.id, amount=amount
        )


async def test_create_gift_insufficient_credits(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 4)
    with pytest.raises(InsufficientCreditsError):
        await create_gift(
            session, sender_account_id=sender.id, tenant_id=t.id, amount=5
        )
    # No partial debit, no token row left behind.
    bal = await session.get(AccountBalance, sender.id)
    assert bal.package_credits == 4
    rows = (await session.execute(select(StartToken))).scalars().all()
    assert rows == []


async def test_list_recent_gifts_status_derivation(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 200)

    active = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=5
    )
    claimed = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=7
    )
    claimed.status = "claimed"
    refunded = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=9
    )
    refunded.status = "refunded"
    await session.flush()

    rows = await list_recent_gifts(
        session, sender_account_id=sender.id, limit=10
    )
    by_code = {r.code: r for r in rows}
    assert by_code[active.code].status == "active"
    assert by_code[claimed.code].status == "claimed"
    assert by_code[refunded.code].status == "refunded"


async def test_list_recent_gifts_orders_desc_and_limits(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 200)
    codes = []
    for _ in range(12):
        tok = await create_gift(
            session, sender_account_id=sender.id, tenant_id=t.id, amount=1
        )
        codes.append(tok.code)
    rows = await list_recent_gifts(
        session, sender_account_id=sender.id, limit=10
    )
    assert len(rows) == 10
    # Most recent first (codes[-1] is newest)
    assert rows[0].code == codes[-1]


async def test_sweep_refunds_expired_unclaimed(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    tok1 = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    tok2 = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=15
    )
    # Force tok1 to expired; leave tok2 active.
    tok1.expires_at = utcnow() - timedelta(seconds=1)
    await session.flush()

    bal_before = (await session.get(AccountBalance, sender.id)).package_credits
    n = await sweep_expired_gifts(session, sender_account_id=sender.id)
    assert n == 1

    bal_after = (await session.get(AccountBalance, sender.id)).package_credits
    assert bal_after == bal_before + 10  # tok1 refunded

    reloaded1 = await session.get(StartToken, tok1.code)
    reloaded2 = await session.get(StartToken, tok2.code)
    assert reloaded1.status == "refunded"
    assert reloaded2.status == "active"

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "gift.refunded"))
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].payload_jsonb["reason"] == "expired"


async def test_sweep_skips_claimed_and_already_refunded(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    claimed = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    claimed.status = "claimed"
    claimed.expires_at = utcnow() - timedelta(days=1)
    refunded = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    refunded.status = "refunded"
    refunded.expires_at = utcnow() - timedelta(days=1)
    await session.flush()

    bal_before = (await session.get(AccountBalance, sender.id)).package_credits
    n = await sweep_expired_gifts(session, sender_account_id=sender.id)
    assert n == 0
    bal_after = (await session.get(AccountBalance, sender.id)).package_credits
    assert bal_after == bal_before


async def test_sweep_idempotent(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    tok.expires_at = utcnow() - timedelta(seconds=1)
    await session.flush()

    n1 = await sweep_expired_gifts(session, sender_account_id=sender.id)
    n2 = await sweep_expired_gifts(session, sender_account_id=sender.id)
    assert n1 == 1
    assert n2 == 0


async def test_expiry_days_get_default(session: AsyncSession):
    t = await _tenant(session)
    assert await get_expiry_days(session, tenant_id=t.id) == DEFAULT_EXPIRY_DAYS


async def test_expiry_days_set_and_get(session: AsyncSession):
    t = await _tenant(session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )
    await set_expiry_days(session, tenant_id=t.id, days=14, by_account_id=acc.id)
    await session.flush()
    assert await get_expiry_days(session, tenant_id=t.id) == 14


@pytest.mark.parametrize("days", [0, -1, MAX_EXPIRY_DAYS + 1, MIN_EXPIRY_DAYS - 1])
async def test_expiry_days_set_rejects_out_of_range(session: AsyncSession, days):
    t = await _tenant(session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )
    with pytest.raises(ValueError):
        await set_expiry_days(
            session, tenant_id=t.id, days=days, by_account_id=acc.id
        )


async def test_expiry_days_reset_removes_override(session: AsyncSession):
    t = await _tenant(session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )
    await set_expiry_days(session, tenant_id=t.id, days=90, by_account_id=acc.id)
    await session.flush()
    await reset_expiry_days(session, tenant_id=t.id, by_account_id=acc.id)
    await session.flush()
    row = await session.get(TenantConfig, (t.id, GIFT_EXPIRY_CONFIG_KEY))
    assert row is None
    assert await get_expiry_days(session, tenant_id=t.id) == DEFAULT_EXPIRY_DAYS
```

- [ ] **Step 2: Run the test to verify it fails**

```
uv run pytest tests/test_gift_domain.py -v
```

Expected: collection fails on `ImportError: cannot import name 'create_gift' from 'quantuum.domain.gifts'`.

- [ ] **Step 3: Write the domain module**

```python
# src/quantuum/domain/gifts.py
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    StartToken,
    StartTokenUse,
    TenantConfig,
)
from quantuum.domain.audit import record_audit
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

GIFT_KIND = "gift"
GIFT_CODE_LENGTH = 8
MAX_GIFT_AMOUNT = 1000
MIN_GIFT_AMOUNT = 1

GIFT_EXPIRY_CONFIG_KEY = "gift.expiry_days"
DEFAULT_EXPIRY_DAYS = 30
MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 365

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_GEN_MAX_RETRIES = 5


class InsufficientCreditsError(Exception):
    """Sender does not have enough package_credits to create the gift."""


@dataclass
class GiftRow:
    code: str
    amount: int
    status: str  # active | claimed | refunded
    expires_at: datetime | None
    claimed_at: datetime | None
    created_at: datetime


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(GIFT_CODE_LENGTH))


async def _generate_gift_code(session: AsyncSession) -> str:
    for _ in range(_GEN_MAX_RETRIES):
        code = _gen_code()
        if (await session.get(StartToken, code)) is None:
            return code
    logger.warning("gift.code_collision_exhausted")
    raise RuntimeError("could not generate unique gift code after retries")


async def get_expiry_days(session: AsyncSession, *, tenant_id: int) -> int:
    row = await session.get(TenantConfig, (tenant_id, GIFT_EXPIRY_CONFIG_KEY))
    if row is None:
        return DEFAULT_EXPIRY_DAYS
    value = row.value_jsonb.get("value")
    if not isinstance(value, int):
        return DEFAULT_EXPIRY_DAYS
    return value


async def set_expiry_days(
    session: AsyncSession,
    *,
    tenant_id: int,
    days: int,
    by_account_id: int,
) -> None:
    if not isinstance(days, int) or days < MIN_EXPIRY_DAYS or days > MAX_EXPIRY_DAYS:
        raise ValueError(
            f"days must be int in [{MIN_EXPIRY_DAYS}, {MAX_EXPIRY_DAYS}], got {days!r}"
        )
    old = await get_expiry_days(session, tenant_id=tenant_id)
    row = await session.get(TenantConfig, (tenant_id, GIFT_EXPIRY_CONFIG_KEY))
    if row is None:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=GIFT_EXPIRY_CONFIG_KEY,
            value_jsonb={"value": days},
            updated_by_account_id=by_account_id,
        )
        session.add(row)
    else:
        row.value_jsonb = {"value": days}
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="gift.config_set",
        entity_type="tenant_config",
        entity_id=GIFT_EXPIRY_CONFIG_KEY,
        payload={"old": old, "new": days},
    )


async def reset_expiry_days(
    session: AsyncSession, *, tenant_id: int, by_account_id: int
) -> None:
    row = await session.get(TenantConfig, (tenant_id, GIFT_EXPIRY_CONFIG_KEY))
    if row is None:
        return
    old = row.value_jsonb.get("value", DEFAULT_EXPIRY_DAYS)
    await session.delete(row)
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="gift.config_set",
        entity_type="tenant_config",
        entity_id=GIFT_EXPIRY_CONFIG_KEY,
        payload={"old": old, "new": DEFAULT_EXPIRY_DAYS, "reset": True},
    )


async def create_gift(
    session: AsyncSession,
    *,
    sender_account_id: int,
    tenant_id: int,
    amount: int,
) -> StartToken:
    if not isinstance(amount, int) or amount < MIN_GIFT_AMOUNT or amount > MAX_GIFT_AMOUNT:
        raise ValueError(
            f"amount must be int in [{MIN_GIFT_AMOUNT}, {MAX_GIFT_AMOUNT}], got {amount!r}"
        )

    bal = await session.get(AccountBalance, sender_account_id)
    if bal is None or bal.package_credits < amount:
        raise InsufficientCreditsError(
            f"sender {sender_account_id} has {0 if bal is None else bal.package_credits} credits, gift needs {amount}"
        )

    days = await get_expiry_days(session, tenant_id=tenant_id)
    code = await _generate_gift_code(session)

    bal.package_credits -= amount
    token = StartToken(
        code=code,
        kind=GIFT_KIND,
        tenant_id=tenant_id,
        owner_account_id=sender_account_id,
        payload={"amount": amount},
        status="active",
        max_uses=1,
        used_count=0,
        expires_at=utcnow() + timedelta(days=days),
    )
    session.add(token)
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=sender_account_id,
        action="gift.created",
        entity_type="start_token",
        entity_id=code,
        payload={"code": code, "amount": amount, "tenant_id": tenant_id},
    )
    return token


async def list_recent_gifts(
    session: AsyncSession, *, sender_account_id: int, limit: int = 10
) -> list[GiftRow]:
    rows = (
        await session.execute(
            select(StartToken)
            .where(
                StartToken.kind == GIFT_KIND,
                StartToken.owner_account_id == sender_account_id,
            )
            .order_by(StartToken.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    # claimed_at for each token (one row at most due to max_uses=1)
    claim_by_code: dict[str, datetime | None] = {}
    if rows:
        codes = [r.code for r in rows]
        for use in (
            await session.execute(
                select(StartTokenUse).where(StartTokenUse.token_code.in_(codes))
            )
        ).scalars().all():
            claim_by_code[use.token_code] = use.claimed_at

    out: list[GiftRow] = []
    for tok in rows:
        amount = int(tok.payload.get("amount", 0))
        # tok.status is already terminal for claimed/refunded; map "active" verbatim.
        out.append(
            GiftRow(
                code=tok.code,
                amount=amount,
                status=tok.status,
                expires_at=tok.expires_at,
                claimed_at=claim_by_code.get(tok.code),
                created_at=tok.created_at,
            )
        )
    return out


async def sweep_expired_gifts(
    session: AsyncSession, *, sender_account_id: int
) -> int:
    now = utcnow()
    candidates = (
        await session.execute(
            select(StartToken).where(
                StartToken.kind == GIFT_KIND,
                StartToken.owner_account_id == sender_account_id,
                StartToken.status == "active",
                StartToken.expires_at.is_not(None),
                StartToken.expires_at <= now,
            )
        )
    ).scalars().all()
    if not candidates:
        return 0

    bal = await session.get(AccountBalance, sender_account_id)
    refunded = 0
    for tok in candidates:
        amount = int(tok.payload.get("amount", 0))
        if amount <= 0:
            tok.status = "refunded"
            continue
        bal.package_credits += amount
        tok.status = "refunded"
        await record_audit(
            session,
            tenant_id=tok.tenant_id,
            actor_account_id=sender_account_id,
            action="gift.refunded",
            entity_type="start_token",
            entity_id=tok.code,
            payload={"code": tok.code, "amount": amount, "reason": "expired"},
        )
        refunded += 1
    await session.flush()
    return refunded
```

- [ ] **Step 4: Run tests until green**

```
uv run pytest tests/test_gift_domain.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Ruff check**

```
uv run ruff check src/quantuum/domain/gifts.py tests/test_gift_domain.py
```

Expected: no issues. If any are reported, fix them in-place.

- [ ] **Step 6: Commit**

```
git add src/quantuum/domain/gifts.py tests/test_gift_domain.py
git commit -m "feat(sp5-t2): domain/gifts.py (create/list/sweep + expiry config)"
```

---

## Task 3 — Gift dispatcher + `/start` surfaces `gift.received`

**Files:**
- Modify: `src/quantuum/bot/handlers/start_tokens.py` (add `handle_gift_token`, register, change `dispatch_start_token` return type)
- Modify: `src/quantuum/bot/handlers/start.py` (capture result, surface `gift.received`)
- Test: `tests/test_start_token_dispatcher.py` (extend with gift cases)

**Context:** `dispatch_start_token` currently returns `None`. We change its return type to `GiftClaimResult | None` so `/start` can render `gift.received`. The SP4 referral handler keeps returning `None` — change is backward-compatible because callers either ignore the return or handle the new envelope.

- [ ] **Step 1: Add failing tests to `tests/test_start_token_dispatcher.py`**

Append these tests (keep existing tests intact):

```python
# tests/test_start_token_dispatcher.py — APPEND
from datetime import timedelta

from quantuum.bot.handlers.start_tokens import GiftClaimResult
from quantuum.db.models import AccountBalance, AuditLog
from quantuum.domain.gifts import GIFT_KIND, create_gift


async def _account_with_credits(session, tenant_id, tg, credits):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.flush()
    return acc


async def test_dispatch_gift_claim_credits_recipient(session):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    recipient = await _account_with_credits(session, t.id, "2001", 0)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )
    resolved = await resolve_start_token(session, code=tok.code, tenant_id=t.id)

    result = await dispatch_start_token(
        session, token=resolved, account_id=recipient.id
    )

    assert isinstance(result, GiftClaimResult)
    assert result.amount == 20

    bal = await session.get(AccountBalance, recipient.id)
    assert bal.package_credits == 20

    reloaded = await session.get(StartToken, tok.code)
    assert reloaded.status == "claimed"
    assert reloaded.used_count == 1

    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.token_code == tok.code)
        )
    ).scalars().one()
    assert use.claimed_at is not None

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "gift.claimed"))
    ).scalars().one()
    assert audit.payload_jsonb["code"] == tok.code
    assert audit.payload_jsonb["amount"] == 20


async def test_dispatch_gift_self_claim_silent(session):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )
    resolved = await resolve_start_token(session, code=tok.code, tenant_id=t.id)

    result = await dispatch_start_token(
        session, token=resolved, account_id=sender.id
    )

    assert result is None
    reloaded = await session.get(StartToken, tok.code)
    assert reloaded.status == "active"
    audit = (
        await session.execute(
            select(AuditLog).where(AuditLog.action == "gift.self_blocked")
        )
    ).scalars().one()
    assert audit.payload_jsonb["code"] == tok.code


async def test_dispatch_gift_malformed_payload_silent(session):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    recipient = await _account_with_credits(session, t.id, "2001", 0)
    # Hand-build a malformed gift token (amount missing / zero)
    bad = StartToken(
        code="GIFTBAD1", kind=GIFT_KIND, tenant_id=t.id,
        owner_account_id=sender.id, payload={"amount": 0},
        status="active", max_uses=1,
    )
    session.add(bad)
    await session.flush()
    resolved = await resolve_start_token(session, code=bad.code, tenant_id=t.id)

    result = await dispatch_start_token(
        session, token=resolved, account_id=recipient.id
    )

    assert result is None
    bal = await session.get(AccountBalance, recipient.id)
    assert bal.package_credits == 0
    reloaded = await session.get(StartToken, bad.code)
    assert reloaded.status == "active"  # untouched


async def test_dispatch_gift_double_claim_aborts_second(session):
    """Sequential second claim sees status='claimed' and bails out."""
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    r1 = await _account_with_credits(session, t.id, "2001", 0)
    r2 = await _account_with_credits(session, t.id, "3001", 0)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )

    resolved1 = await resolve_start_token(session, code=tok.code, tenant_id=t.id)
    result1 = await dispatch_start_token(session, token=resolved1, account_id=r1.id)
    assert isinstance(result1, GiftClaimResult)

    # Second resolve will now return None (status == 'claimed'), so dispatch is
    # never called from /start. We exercise the handler directly to prove the
    # in-handler guard works even if a stale token object is passed.
    stale = await session.get(StartToken, tok.code)
    # Force-pretend it's still "active" in the caller's view:
    stale.status = "active"
    result2 = await dispatch_start_token(session, token=stale, account_id=r2.id)
    assert result2 is None
    bal_r2 = await session.get(AccountBalance, r2.id)
    assert bal_r2.package_credits == 0


async def test_dispatch_gift_feature_flag_off_silent(session):
    from quantuum.domain.tenant_features import set_feature_enabled

    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    recipient = await _account_with_credits(session, t.id, "2001", 0)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )
    # Turn the flag off AFTER creation.
    await set_feature_enabled(
        session,
        tenant_id=t.id,
        key="gifts",
        enabled=False,
        by_account_id=sender.id,
    )
    await session.flush()

    resolved = await resolve_start_token(session, code=tok.code, tenant_id=t.id)
    result = await dispatch_start_token(
        session, token=resolved, account_id=recipient.id
    )
    assert result is None
    bal = await session.get(AccountBalance, recipient.id)
    assert bal.package_credits == 0
```

Note: `set_feature_enabled` will work for `"gifts"` only after Task 5 lands the key in `FEATURE_KEYS`. Mark this single test with `@pytest.mark.skip(reason="enabled after T5 adds gifts to FEATURE_KEYS")` for the T3 commit and remove the skip in T5 — adjust the test then.

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_start_token_dispatcher.py -v
```

Expected: collection error for `GiftClaimResult`. SP4 referral tests still pass.

- [ ] **Step 3: Modify `src/quantuum/bot/handlers/start_tokens.py`**

Top of file — add imports and dataclass; update return type of `dispatch_start_token`:

```python
from dataclasses import dataclass

from quantuum.db.models import AccountBalance, StartToken, StartTokenUse
from quantuum.domain.gifts import GIFT_KIND
from quantuum.domain.tenant_features import is_feature_enabled
# (keep the existing imports above)


@dataclass
class GiftClaimResult:
    amount: int


async def dispatch_start_token(
    session: AsyncSession, *, token: StartToken, account_id: int
) -> "GiftClaimResult | None":
    handler = _HANDLERS.get(token.kind)
    if handler is None:
        logger.warning("start_token.unknown_kind", kind=token.kind, code=token.code)
        return None
    return await handler(session, token=token, account_id=account_id)
```

Add the gift handler near the existing `handle_referral_token`:

```python
async def handle_gift_token(
    session: AsyncSession, *, token: StartToken, account_id: int
) -> "GiftClaimResult | None":
    if token.owner_account_id == account_id:
        await record_audit(
            session,
            tenant_id=token.tenant_id,
            actor_account_id=account_id,
            action="gift.self_blocked",
            entity_type="start_token",
            entity_id=token.code,
            payload={"code": token.code, "owner_account_id": token.owner_account_id},
        )
        return None

    if not await is_feature_enabled(session, token.tenant_id, "gifts"):
        return None

    amount = int(token.payload.get("amount", 0))
    if amount <= 0:
        return None

    locked = (
        await session.execute(
            select(StartToken).where(StartToken.code == token.code).with_for_update()
        )
    ).scalar_one()
    if locked.status != "active" or (
        locked.max_uses is not None and locked.used_count >= locked.max_uses
    ):
        return None

    session.add(StartTokenUse(
        token_code=locked.code,
        account_id=account_id,
        used_at=utcnow(),
        claimed_at=utcnow(),
    ))
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        # Defensive — middleware seeds AccountBalance, but a hand-built test could skip.
        return None
    bal.package_credits += amount
    locked.status = "claimed"
    locked.used_count = (locked.used_count or 0) + 1
    await session.flush()
    await record_audit(
        session,
        tenant_id=locked.tenant_id,
        actor_account_id=account_id,
        action="gift.claimed",
        entity_type="start_token",
        entity_id=locked.code,
        payload={
            "code": locked.code,
            "amount": amount,
            "sender_account_id": locked.owner_account_id,
        },
    )
    return GiftClaimResult(amount=amount)


_HANDLERS = {
    REFERRAL_KIND: handle_referral_token,
    GIFT_KIND: handle_gift_token,
}
```

Also bump the referral handler's signature for type consistency: change its annotation to `-> "GiftClaimResult | None"` (it still returns `None`).

- [ ] **Step 4: Update `src/quantuum/bot/handlers/start.py`**

Current code at `src/quantuum/bot/handlers/start.py:23-31` looks like:

```python
payload = parse_start_payload(message.text)
if payload:
    async with get_sessionmaker()() as session:
        token = await resolve_start_token(session, code=payload, tenant_id=tenant_id)
        if token is None:
            await message.answer(await i18n("invite.unknown_code"))
        else:
            await dispatch_start_token(session, token=token, account_id=account.id)
        await session.commit()
```

Capture the result and surface `gift.received`:

```python
payload = parse_start_payload(message.text)
if payload:
    async with get_sessionmaker()() as session:
        token = await resolve_start_token(session, code=payload, tenant_id=tenant_id)
        if token is None:
            await message.answer(await i18n("invite.unknown_code"))
            dispatch_result = None
        else:
            dispatch_result = await dispatch_start_token(
                session, token=token, account_id=account.id
            )
        await session.commit()
    if isinstance(dispatch_result, GiftClaimResult):
        await message.answer(
            await i18n("gift.received", amount=dispatch_result.amount)
        )
```

Add `GiftClaimResult` to the imports at the top of the file.

Note on the `gift.received` translation: until Task 4 ships the i18n entry, this call will fall back to the key name. That's fine for the dispatcher tests; the handler doesn't assert on the user-facing text in T3.

- [ ] **Step 5: Run dispatcher tests until green**

```
uv run pytest tests/test_start_token_dispatcher.py -v
```

Expected: all pass (the `gifts`-flag-off test is `@skip`).

- [ ] **Step 6: Run SP4 dispatch + referral tests for no regression**

```
uv run pytest tests/test_referral_domain.py tests/test_consume_quota_referral_integration.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```
git add src/quantuum/bot/handlers/start_tokens.py \
        src/quantuum/bot/handlers/start.py \
        tests/test_start_token_dispatcher.py
git commit -m "feat(sp5-t3): gift dispatcher + /start surfaces gift.received"
```

---

## Task 4 — i18n seed (30 keys × 10 locales)

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (append entries to `BASE_STRINGS`)
- Modify: `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` (append entries to `TRANSLATIONS`)
- Create: `tests/test_gift_i18n.py`

**Context:** SP4 used the same pattern. `BASE_STRINGS` holds `ru` + `en` for each key; the 8 other-locale modules each export a `TRANSLATIONS` dict that the i18n loader merges into `BASE_STRINGS` at startup. Placeholder integrity is enforced via a parametrized test (the same approach SP4 T3 used after the fix commit `0d7003f`).

**The 30 keys (Russian + English):**

```python
# Keys to add. Use the column header for placeholder hints.
# (key, ru, en, placeholders)
GIFT_KEYS = [
    ("btn.gift",
        "Подарок",
        "Gift",
        ()),
    ("gift.title",
        "Подарок другу",
        "Gift a friend",
        ()),
    ("gift.balance_line",
        "Доступно: {balance}",
        "Available: {balance}",
        ("balance",)),
    ("gift.amount_prompt",
        "Введите сумму подарка (1–{max}):",
        "Enter gift amount (1–{max}):",
        ("max",)),
    ("gift.cancel_hint",
        "Отправьте /cancel чтобы отменить.",
        "Send /cancel to abort.",
        ()),
    ("gift.too_small",
        "Минимум — 1 кредит.",
        "Minimum is 1 credit.",
        ()),
    ("gift.too_large",
        "Максимум — {max} кредитов.",
        "Maximum is {max} credits.",
        ("max",)),
    ("gift.not_a_number",
        "Это не число. Введите целое число.",
        "That's not a number. Enter a whole number.",
        ()),
    ("gift.no_balance",
        "У вас нет кредитов, чтобы подарить.",
        "You have no credits to gift.",
        ()),
    ("gift.created",
        "Подарок на {amount} кредитов готов!\n\nСсылка: {link}",
        "Gift of {amount} credits is ready!\n\nLink: {link}",
        ("amount", "link")),
    ("gift.share_text",
        "Тебе подарок! Открой бота и получи кредиты.",
        "A gift for you! Open the bot to claim your credits.",
        ()),
    ("gift.disabled",
        "Подарки сейчас недоступны.",
        "Gifts are currently unavailable.",
        ()),
    ("gift.received",
        "Вы получили подарок: {amount} кредитов!",
        "You received a gift: {amount} credits!",
        ("amount",)),
    ("gift.self_blocked",
        "Нельзя получить собственный подарок.",
        "You can't claim your own gift.",
        ()),
    ("gift.history_title",
        "Ваши подарки",
        "Your gifts",
        ()),
    ("gift.history_empty",
        "Пока пусто.",
        "Nothing yet.",
        ()),
    ("gift.history_row",
        "{date} — {amount} кр. — {status}",
        "{date} — {amount} cr. — {status}",
        ("date", "amount", "status")),
    ("gift.status.active",
        "ожидает",
        "pending",
        ()),
    ("gift.status.claimed",
        "получен",
        "claimed",
        ()),
    ("gift.status.refunded",
        "возвращён",
        "refunded",
        ()),
    ("gift.btn.create_new",
        "Создать новый",
        "Create new",
        ()),
    ("owner.gifts.menu_button",
        "Подарки",
        "Gifts",
        ()),
    ("owner.gifts.title",
        "Подарки",
        "Gifts",
        ()),
    ("owner.gifts.current_value",
        "Срок жизни подарка: {value} дней.",
        "Gift lifetime: {value} days.",
        ("value",)),
    ("owner.gifts.prompt",
        "Введите срок жизни подарка в днях ({min}–{max}):",
        "Enter gift lifetime in days ({min}–{max}):",
        ("min", "max")),
    ("owner.gifts.saved",
        "Сохранено.",
        "Saved.",
        ()),
    ("owner.gifts.reset",
        "Сброшено до значения по умолчанию.",
        "Reset to default.",
        ()),
    ("owner.gifts.too_small",
        "Минимум — {min} день.",
        "Minimum is {min} day.",
        ("min",)),
    ("owner.gifts.too_large",
        "Максимум — {max} дней.",
        "Maximum is {max} days.",
        ("max",)),
    ("owner.gifts.not_a_number",
        "Введите целое число.",
        "Enter a whole number.",
        ()),
    ("owner.gifts.cancel_hint",
        "Отправьте /cancel чтобы отменить.",
        "Send /cancel to abort.",
        ()),
]
```

Total: 31 entries (one more than the 30 listed in the spec because the spec rolled `owner.gifts.menu_button` and `owner.gifts.title` into one row; here they're separate to avoid coupling button text and screen header). Keep all 31.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gift_i18n.py
import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

GIFT_KEYS = [
    "btn.gift", "gift.title", "gift.balance_line", "gift.amount_prompt",
    "gift.cancel_hint", "gift.too_small", "gift.too_large", "gift.not_a_number",
    "gift.no_balance", "gift.created", "gift.share_text", "gift.disabled",
    "gift.received", "gift.self_blocked", "gift.history_title",
    "gift.history_empty", "gift.history_row", "gift.status.active",
    "gift.status.claimed", "gift.status.refunded", "gift.btn.create_new",
    "owner.gifts.menu_button", "owner.gifts.title", "owner.gifts.current_value",
    "owner.gifts.prompt", "owner.gifts.saved", "owner.gifts.reset",
    "owner.gifts.too_small", "owner.gifts.too_large", "owner.gifts.not_a_number",
    "owner.gifts.cancel_hint",
]

PLACEHOLDERS = {
    "gift.balance_line": {"balance"},
    "gift.amount_prompt": {"max"},
    "gift.too_large": {"max"},
    "gift.created": {"amount", "link"},
    "gift.received": {"amount"},
    "gift.history_row": {"date", "amount", "status"},
    "owner.gifts.current_value": {"value"},
    "owner.gifts.prompt": {"min", "max"},
    "owner.gifts.too_small": {"min"},
    "owner.gifts.too_large": {"max"},
}

LOCALE_MODULES = {
    "de": de.TRANSLATIONS, "es": es.TRANSLATIONS, "fr": fr.TRANSLATIONS,
    "hi": hi.TRANSLATIONS, "it": it.TRANSLATIONS, "pt": pt.TRANSLATIONS,
    "tr": tr.TRANSLATIONS, "zh": zh.TRANSLATIONS,
}


@pytest.mark.parametrize("key", GIFT_KEYS)
def test_key_present_in_base_strings_ru_en(key):
    assert key in BASE_STRINGS, f"missing in BASE_STRINGS: {key}"
    assert "ru" in BASE_STRINGS[key], f"BASE_STRINGS[{key}] missing 'ru'"
    assert "en" in BASE_STRINGS[key], f"BASE_STRINGS[{key}] missing 'en'"


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key", GIFT_KEYS)
def test_key_present_in_locale(locale_code, translations, key):
    assert key in translations, f"missing in {locale_code}: {key}"


@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_base(key, expected):
    import re
    pattern = re.compile(r"\{(\w+)\}")
    for lang in ("ru", "en"):
        found = set(pattern.findall(BASE_STRINGS[key][lang]))
        assert found == expected, f"BASE_STRINGS[{key}][{lang}] placeholders {found} != {expected}"


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_locale(locale_code, translations, key, expected):
    import re
    pattern = re.compile(r"\{(\w+)\}")
    found = set(pattern.findall(translations[key]))
    assert found == expected, f"{locale_code}[{key}] placeholders {found} != {expected}"
```

- [ ] **Step 2: Run the test to verify it fails**

```
uv run pytest tests/test_gift_i18n.py -v
```

Expected: many failures (`missing in BASE_STRINGS: ...`).

- [ ] **Step 3: Append entries to `BASE_STRINGS`**

Open `src/quantuum/i18n/seed_strings.py` and add each key from the table above to `BASE_STRINGS`. Use the same dict-of-dicts shape as the existing entries: each value is `{"ru": "<ru text>", "en": "<en text>"}`.

Example placement (group with other btn keys):

```python
"btn.gift": {"ru": "Подарок", "en": "Gift"},
```

Repeat for all 31 keys, placing them near related sections (gift.* near other readings/UI, owner.gifts.* near owner.referrals.*).

- [ ] **Step 4: Append entries to each locale module**

For each of `de.py`, `es.py`, `fr.py`, `hi.py`, `it.py`, `pt.py`, `tr.py`, `zh.py`, add the 31 keys to the `TRANSLATIONS` dict.

Translations for each locale follow the same content as English but localised. To keep this plan compact, use these translations (cross-check with native speakers post-merge — for v1 it's better to ship plausibly-translated strings than to block on perfection):

```python
# de.py — APPEND to TRANSLATIONS
"btn.gift": "Geschenk",
"gift.title": "Verschenke an einen Freund",
"gift.balance_line": "Verfügbar: {balance}",
"gift.amount_prompt": "Geschenkbetrag eingeben (1–{max}):",
"gift.cancel_hint": "Sende /cancel zum Abbrechen.",
"gift.too_small": "Mindestens 1 Kredit.",
"gift.too_large": "Maximal {max} Kredits.",
"gift.not_a_number": "Das ist keine Zahl. Bitte ganze Zahl eingeben.",
"gift.no_balance": "Du hast keine Kredits zum Verschenken.",
"gift.created": "Geschenk über {amount} Kredits ist bereit!\n\nLink: {link}",
"gift.share_text": "Ein Geschenk für dich! Öffne den Bot, um deine Kredits einzulösen.",
"gift.disabled": "Geschenke sind derzeit nicht verfügbar.",
"gift.received": "Du hast ein Geschenk erhalten: {amount} Kredits!",
"gift.self_blocked": "Du kannst dein eigenes Geschenk nicht einlösen.",
"gift.history_title": "Deine Geschenke",
"gift.history_empty": "Noch leer.",
"gift.history_row": "{date} — {amount} Kr. — {status}",
"gift.status.active": "ausstehend",
"gift.status.claimed": "eingelöst",
"gift.status.refunded": "erstattet",
"gift.btn.create_new": "Neu erstellen",
"owner.gifts.menu_button": "Geschenke",
"owner.gifts.title": "Geschenke",
"owner.gifts.current_value": "Geschenkdauer: {value} Tage.",
"owner.gifts.prompt": "Geschenkdauer in Tagen eingeben ({min}–{max}):",
"owner.gifts.saved": "Gespeichert.",
"owner.gifts.reset": "Auf Standard zurückgesetzt.",
"owner.gifts.too_small": "Mindestens {min} Tag.",
"owner.gifts.too_large": "Maximal {max} Tage.",
"owner.gifts.not_a_number": "Bitte ganze Zahl eingeben.",
"owner.gifts.cancel_hint": "Sende /cancel zum Abbrechen.",
```

```python
# es.py
"btn.gift": "Regalo",
"gift.title": "Regala a un amigo",
"gift.balance_line": "Disponible: {balance}",
"gift.amount_prompt": "Ingresa el monto del regalo (1–{max}):",
"gift.cancel_hint": "Envía /cancel para cancelar.",
"gift.too_small": "Mínimo 1 crédito.",
"gift.too_large": "Máximo {max} créditos.",
"gift.not_a_number": "No es un número. Ingresa un número entero.",
"gift.no_balance": "No tienes créditos para regalar.",
"gift.created": "¡Regalo de {amount} créditos listo!\n\nEnlace: {link}",
"gift.share_text": "¡Un regalo para ti! Abre el bot para reclamar tus créditos.",
"gift.disabled": "Los regalos no están disponibles ahora.",
"gift.received": "¡Recibiste un regalo: {amount} créditos!",
"gift.self_blocked": "No puedes reclamar tu propio regalo.",
"gift.history_title": "Tus regalos",
"gift.history_empty": "Aún vacío.",
"gift.history_row": "{date} — {amount} cr. — {status}",
"gift.status.active": "pendiente",
"gift.status.claimed": "reclamado",
"gift.status.refunded": "reembolsado",
"gift.btn.create_new": "Crear nuevo",
"owner.gifts.menu_button": "Regalos",
"owner.gifts.title": "Regalos",
"owner.gifts.current_value": "Vida del regalo: {value} días.",
"owner.gifts.prompt": "Ingresa la vida del regalo en días ({min}–{max}):",
"owner.gifts.saved": "Guardado.",
"owner.gifts.reset": "Restablecido al valor predeterminado.",
"owner.gifts.too_small": "Mínimo {min} día.",
"owner.gifts.too_large": "Máximo {max} días.",
"owner.gifts.not_a_number": "Ingresa un número entero.",
"owner.gifts.cancel_hint": "Envía /cancel para cancelar.",
```

```python
# fr.py
"btn.gift": "Cadeau",
"gift.title": "Offrir à un ami",
"gift.balance_line": "Disponible : {balance}",
"gift.amount_prompt": "Entrez le montant du cadeau (1–{max}) :",
"gift.cancel_hint": "Envoyez /cancel pour annuler.",
"gift.too_small": "Minimum 1 crédit.",
"gift.too_large": "Maximum {max} crédits.",
"gift.not_a_number": "Ce n'est pas un nombre. Entrez un nombre entier.",
"gift.no_balance": "Vous n'avez pas de crédits à offrir.",
"gift.created": "Cadeau de {amount} crédits prêt !\n\nLien : {link}",
"gift.share_text": "Un cadeau pour toi ! Ouvre le bot pour réclamer tes crédits.",
"gift.disabled": "Les cadeaux ne sont pas disponibles actuellement.",
"gift.received": "Vous avez reçu un cadeau : {amount} crédits !",
"gift.self_blocked": "Vous ne pouvez pas réclamer votre propre cadeau.",
"gift.history_title": "Vos cadeaux",
"gift.history_empty": "Encore vide.",
"gift.history_row": "{date} — {amount} cr. — {status}",
"gift.status.active": "en attente",
"gift.status.claimed": "réclamé",
"gift.status.refunded": "remboursé",
"gift.btn.create_new": "Créer nouveau",
"owner.gifts.menu_button": "Cadeaux",
"owner.gifts.title": "Cadeaux",
"owner.gifts.current_value": "Durée de vie du cadeau : {value} jours.",
"owner.gifts.prompt": "Entrez la durée de vie du cadeau en jours ({min}–{max}) :",
"owner.gifts.saved": "Sauvegardé.",
"owner.gifts.reset": "Réinitialisé à la valeur par défaut.",
"owner.gifts.too_small": "Minimum {min} jour.",
"owner.gifts.too_large": "Maximum {max} jours.",
"owner.gifts.not_a_number": "Entrez un nombre entier.",
"owner.gifts.cancel_hint": "Envoyez /cancel pour annuler.",
```

```python
# hi.py
"btn.gift": "उपहार",
"gift.title": "मित्र को उपहार दें",
"gift.balance_line": "उपलब्ध: {balance}",
"gift.amount_prompt": "उपहार राशि दर्ज करें (1–{max}):",
"gift.cancel_hint": "रद्द करने के लिए /cancel भेजें।",
"gift.too_small": "न्यूनतम 1 क्रेडिट।",
"gift.too_large": "अधिकतम {max} क्रेडिट।",
"gift.not_a_number": "यह संख्या नहीं है। पूर्णांक दर्ज करें।",
"gift.no_balance": "उपहार देने के लिए आपके पास क्रेडिट नहीं हैं।",
"gift.created": "{amount} क्रेडिट का उपहार तैयार है!\n\nलिंक: {link}",
"gift.share_text": "तुम्हारे लिए उपहार! क्रेडिट प्राप्त करने के लिए बॉट खोलो।",
"gift.disabled": "उपहार अभी उपलब्ध नहीं हैं।",
"gift.received": "आपको उपहार मिला: {amount} क्रेडिट!",
"gift.self_blocked": "आप अपना उपहार स्वयं प्राप्त नहीं कर सकते।",
"gift.history_title": "आपके उपहार",
"gift.history_empty": "अभी खाली।",
"gift.history_row": "{date} — {amount} क्र. — {status}",
"gift.status.active": "लंबित",
"gift.status.claimed": "प्राप्त",
"gift.status.refunded": "वापस",
"gift.btn.create_new": "नया बनाएं",
"owner.gifts.menu_button": "उपहार",
"owner.gifts.title": "उपहार",
"owner.gifts.current_value": "उपहार अवधि: {value} दिन।",
"owner.gifts.prompt": "उपहार अवधि दिनों में दर्ज करें ({min}–{max}):",
"owner.gifts.saved": "सहेजा गया।",
"owner.gifts.reset": "डिफ़ॉल्ट पर रीसेट।",
"owner.gifts.too_small": "न्यूनतम {min} दिन।",
"owner.gifts.too_large": "अधिकतम {max} दिन।",
"owner.gifts.not_a_number": "पूर्णांक दर्ज करें।",
"owner.gifts.cancel_hint": "रद्द करने के लिए /cancel भेजें।",
```

```python
# it.py
"btn.gift": "Regalo",
"gift.title": "Regala a un amico",
"gift.balance_line": "Disponibile: {balance}",
"gift.amount_prompt": "Inserisci l'importo del regalo (1–{max}):",
"gift.cancel_hint": "Invia /cancel per annullare.",
"gift.too_small": "Minimo 1 credito.",
"gift.too_large": "Massimo {max} crediti.",
"gift.not_a_number": "Non è un numero. Inserisci un numero intero.",
"gift.no_balance": "Non hai crediti da regalare.",
"gift.created": "Regalo di {amount} crediti pronto!\n\nLink: {link}",
"gift.share_text": "Un regalo per te! Apri il bot per riscattare i tuoi crediti.",
"gift.disabled": "I regali non sono disponibili al momento.",
"gift.received": "Hai ricevuto un regalo: {amount} crediti!",
"gift.self_blocked": "Non puoi riscattare il tuo regalo.",
"gift.history_title": "I tuoi regali",
"gift.history_empty": "Ancora vuoto.",
"gift.history_row": "{date} — {amount} cr. — {status}",
"gift.status.active": "in attesa",
"gift.status.claimed": "riscattato",
"gift.status.refunded": "rimborsato",
"gift.btn.create_new": "Crea nuovo",
"owner.gifts.menu_button": "Regali",
"owner.gifts.title": "Regali",
"owner.gifts.current_value": "Durata del regalo: {value} giorni.",
"owner.gifts.prompt": "Inserisci la durata del regalo in giorni ({min}–{max}):",
"owner.gifts.saved": "Salvato.",
"owner.gifts.reset": "Reimpostato al valore predefinito.",
"owner.gifts.too_small": "Minimo {min} giorno.",
"owner.gifts.too_large": "Massimo {max} giorni.",
"owner.gifts.not_a_number": "Inserisci un numero intero.",
"owner.gifts.cancel_hint": "Invia /cancel per annullare.",
```

```python
# pt.py
"btn.gift": "Presente",
"gift.title": "Presenteie um amigo",
"gift.balance_line": "Disponível: {balance}",
"gift.amount_prompt": "Digite o valor do presente (1–{max}):",
"gift.cancel_hint": "Envie /cancel para cancelar.",
"gift.too_small": "Mínimo 1 crédito.",
"gift.too_large": "Máximo {max} créditos.",
"gift.not_a_number": "Não é um número. Digite um número inteiro.",
"gift.no_balance": "Você não tem créditos para presentear.",
"gift.created": "Presente de {amount} créditos pronto!\n\nLink: {link}",
"gift.share_text": "Um presente pra você! Abra o bot para resgatar seus créditos.",
"gift.disabled": "Presentes não estão disponíveis no momento.",
"gift.received": "Você recebeu um presente: {amount} créditos!",
"gift.self_blocked": "Você não pode resgatar seu próprio presente.",
"gift.history_title": "Seus presentes",
"gift.history_empty": "Ainda vazio.",
"gift.history_row": "{date} — {amount} cr. — {status}",
"gift.status.active": "pendente",
"gift.status.claimed": "resgatado",
"gift.status.refunded": "reembolsado",
"gift.btn.create_new": "Criar novo",
"owner.gifts.menu_button": "Presentes",
"owner.gifts.title": "Presentes",
"owner.gifts.current_value": "Validade do presente: {value} dias.",
"owner.gifts.prompt": "Digite a validade do presente em dias ({min}–{max}):",
"owner.gifts.saved": "Salvo.",
"owner.gifts.reset": "Redefinido para padrão.",
"owner.gifts.too_small": "Mínimo {min} dia.",
"owner.gifts.too_large": "Máximo {max} dias.",
"owner.gifts.not_a_number": "Digite um número inteiro.",
"owner.gifts.cancel_hint": "Envie /cancel para cancelar.",
```

```python
# tr.py
"btn.gift": "Hediye",
"gift.title": "Bir arkadaşa hediye et",
"gift.balance_line": "Mevcut: {balance}",
"gift.amount_prompt": "Hediye miktarını girin (1–{max}):",
"gift.cancel_hint": "İptal etmek için /cancel gönderin.",
"gift.too_small": "En az 1 kredi.",
"gift.too_large": "En fazla {max} kredi.",
"gift.not_a_number": "Bu sayı değil. Tam sayı girin.",
"gift.no_balance": "Hediye edecek krediniz yok.",
"gift.created": "{amount} kredilik hediye hazır!\n\nLink: {link}",
"gift.share_text": "Sana bir hediye! Kredilerini almak için botu aç.",
"gift.disabled": "Hediyeler şu anda kullanılamıyor.",
"gift.received": "Bir hediye aldın: {amount} kredi!",
"gift.self_blocked": "Kendi hediyenizi alamazsınız.",
"gift.history_title": "Hediyeleriniz",
"gift.history_empty": "Henüz boş.",
"gift.history_row": "{date} — {amount} kr. — {status}",
"gift.status.active": "beklemede",
"gift.status.claimed": "alındı",
"gift.status.refunded": "iade edildi",
"gift.btn.create_new": "Yeni oluştur",
"owner.gifts.menu_button": "Hediyeler",
"owner.gifts.title": "Hediyeler",
"owner.gifts.current_value": "Hediye ömrü: {value} gün.",
"owner.gifts.prompt": "Hediye ömrünü gün olarak girin ({min}–{max}):",
"owner.gifts.saved": "Kaydedildi.",
"owner.gifts.reset": "Varsayılana sıfırlandı.",
"owner.gifts.too_small": "En az {min} gün.",
"owner.gifts.too_large": "En fazla {max} gün.",
"owner.gifts.not_a_number": "Tam sayı girin.",
"owner.gifts.cancel_hint": "İptal etmek için /cancel gönderin.",
```

```python
# zh.py
"btn.gift": "礼物",
"gift.title": "送给朋友",
"gift.balance_line": "可用：{balance}",
"gift.amount_prompt": "输入礼物金额（1–{max}）：",
"gift.cancel_hint": "发送 /cancel 取消。",
"gift.too_small": "最少 1 个积分。",
"gift.too_large": "最多 {max} 个积分。",
"gift.not_a_number": "这不是数字。请输入整数。",
"gift.no_balance": "您没有可赠送的积分。",
"gift.created": "{amount} 积分的礼物已就绪！\n\n链接：{link}",
"gift.share_text": "送你一份礼物！打开机器人领取积分。",
"gift.disabled": "礼物当前不可用。",
"gift.received": "您收到了礼物：{amount} 积分！",
"gift.self_blocked": "您不能领取自己的礼物。",
"gift.history_title": "您的礼物",
"gift.history_empty": "暂无。",
"gift.history_row": "{date} — {amount} 积分 — {status}",
"gift.status.active": "待领取",
"gift.status.claimed": "已领取",
"gift.status.refunded": "已退还",
"gift.btn.create_new": "新建",
"owner.gifts.menu_button": "礼物",
"owner.gifts.title": "礼物",
"owner.gifts.current_value": "礼物有效期：{value} 天。",
"owner.gifts.prompt": "输入礼物有效期天数（{min}–{max}）：",
"owner.gifts.saved": "已保存。",
"owner.gifts.reset": "已重置为默认值。",
"owner.gifts.too_small": "最少 {min} 天。",
"owner.gifts.too_large": "最多 {max} 天。",
"owner.gifts.not_a_number": "请输入整数。",
"owner.gifts.cancel_hint": "发送 /cancel 取消。",
```

- [ ] **Step 5: Run tests until green**

```
uv run pytest tests/test_gift_i18n.py -v
```

Expected: all PASS (≈ 31 + 248 + 10 + 80 = ~370 parametrized cases).

- [ ] **Step 6: Commit**

```
git add src/quantuum/i18n/seed_strings.py \
        src/quantuum/i18n/translations/de.py src/quantuum/i18n/translations/es.py \
        src/quantuum/i18n/translations/fr.py src/quantuum/i18n/translations/hi.py \
        src/quantuum/i18n/translations/it.py src/quantuum/i18n/translations/pt.py \
        src/quantuum/i18n/translations/tr.py src/quantuum/i18n/translations/zh.py \
        tests/test_gift_i18n.py
git commit -m "feat(sp5-t4): i18n seed 31 gift keys × 10 locales"
```

---

## Task 5 — `/gift` handler, FSM, menu button, tenant flag

**Files:**
- Create: `src/quantuum/bot/handlers/gift.py`
- Create: `tests/test_gift_handler.py`
- Modify: `src/quantuum/bot/ui/text.py:6-9` — add `"btn.gift"` to `MENU_BUTTON_KEYS`
- Modify: `src/quantuum/bot/ui/keyboards.py` — add `btn.gift` row in `main_menu_kb` gated on the `gifts` flag
- Modify: `src/quantuum/bot/app.py` — `dp.include_router(gift.router)`
- Modify: `src/quantuum/domain/tenant_features.py` — append `"gifts"` to `FEATURE_KEYS`
- Modify: `tests/test_tenant_features_domain.py` — bump 13→14 inventory assertions
- Modify: `tests/test_start_token_dispatcher.py` — remove the `@pytest.mark.skip` on the flag-off test added in T3

**Context:** Mirror `src/quantuum/bot/handlers/invite.py` for the screen wiring. `Account` is middleware-injected; the FSM uses aiogram's `StatesGroup` and `FSMContext`. `_GIFT_LABELS = text.menu_button_labels("btn.gift")` resolves localized labels for the reply-keyboard router. Use `https://t.me/share/url?url=<quoted>&text=<quoted>` for the share button (`urllib.parse.quote` with `safe=""`).

- [ ] **Step 1: Write the failing test file**

```python
# tests/test_gift_handler.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.bot.handlers.gift import show_gift_screen
from quantuum.bot.ui.text import MENU_BUTTON_KEYS
from quantuum.db.models import AccountBalance


def test_btn_gift_in_menu_button_keys():
    assert "btn.gift" in MENU_BUTTON_KEYS


async def _seed_sender(session, t_id, tg="1001", credits=50):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t_id, tg_user_id=tg
    )
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.flush()
    return acc


async def test_show_gift_screen_renders_balance_and_history(session, default_tenant):
    sender = await _seed_sender(session, default_tenant.id)

    msg = MagicMock()
    msg.answer = AsyncMock()
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}:{kw}>")

    await show_gift_screen(
        msg, account_id=sender.id, tenant_id=default_tenant.id, i18n=i18n
    )
    body = msg.answer.await_args.args[0]
    assert "gift.title" in body
    assert "gift.balance_line" in body
    assert "gift.history_empty" in body


async def test_show_gift_screen_blocked_when_feature_off(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.tenant_features import set_feature_enabled

    sender = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="1001"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="gifts",
        enabled=False,
        by_account_id=sender.id,
    )
    await session.commit()

    msg = MagicMock()
    msg.answer = AsyncMock()
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")

    await show_gift_screen(
        msg, account_id=sender.id, tenant_id=default_tenant.id, i18n=i18n
    )
    body = msg.answer.await_args.args[0]
    assert body == "<gift.disabled>"


async def test_show_gift_screen_runs_sweep(session, default_tenant):
    from datetime import timedelta

    from quantuum.common.datetime import utcnow
    from quantuum.domain.gifts import create_gift

    sender = await _seed_sender(session, default_tenant.id, credits=100)
    tok = await create_gift(
        session, sender_account_id=sender.id,
        tenant_id=default_tenant.id, amount=15,
    )
    tok.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()

    msg = MagicMock()
    msg.answer = AsyncMock()
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}:{kw}>")

    await show_gift_screen(
        msg, account_id=sender.id, tenant_id=default_tenant.id, i18n=i18n
    )

    # After the screen runs, the sender should have been refunded.
    bal = await session.get(AccountBalance, sender.id)
    # _seed_sender set 100, create_gift debited 15 (→85), sweep should refund (→100).
    # We need a fresh session because show_gift_screen opens its own:
    # the test session must observe the committed effect.
    await session.refresh(bal)
    assert bal.package_credits == 100


async def test_create_flow_emits_link(session, default_tenant, monkeypatch):
    """End-to-end of the text handler for the amount state."""
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.storage.base import StorageKey

    sender = await _seed_sender(session, default_tenant.id, credits=50)
    # Set bot_username so the link can be built.
    from quantuum.db.models import TenantBot
    session.add(TenantBot(
        tenant_id=default_tenant.id,
        bot_username="t_bot",
        bot_token_enc=b"x",
        webhook_secret_path="/wh",
    ))
    await session.commit()

    msg = MagicMock()
    msg.text = "10"
    msg.from_user = MagicMock()
    msg.from_user.id = 1001
    msg.answer = AsyncMock()

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"account_id": sender.id, "tenant_id": default_tenant.id})
    state.clear = AsyncMock()

    i18n = AsyncMock(side_effect=lambda key, **kw: f"{key}:{kw}")

    from quantuum.bot.handlers.gift import on_amount_received
    await on_amount_received(msg, state=state, i18n=i18n,
                             account=MagicMock(id=sender.id),
                             tenant_id=default_tenant.id)

    body = msg.answer.await_args.args[0]
    assert "gift.created" in body
    assert "https://t.me/t_bot?start=" in body
```

- [ ] **Step 2: Run the failing test**

```
uv run pytest tests/test_gift_handler.py -v
```

Expected: `ImportError: cannot import name 'show_gift_screen'`.

- [ ] **Step 3: Add `"gifts"` to `FEATURE_KEYS`**

Open `src/quantuum/domain/tenant_features.py` and append `"gifts"` to `FEATURE_KEYS` (after the existing `"referrals"`).

- [ ] **Step 4: Bump inventory tests**

Open `tests/test_tenant_features_domain.py`:

- `test_feature_keys_inventory`: add `"gifts"` to the asserted set; change `assert len(FEATURE_KEYS) == 13` to `== 14`.
- `test_list_reflects_overrides`: change `assert len(states) == 13` to `== 14`.

- [ ] **Step 5: Add `"btn.gift"` to `MENU_BUTTON_KEYS`**

In `src/quantuum/bot/ui/text.py:6-9`, current value is:

```python
MENU_BUTTON_KEYS = (
    "btn.generate", "btn.ask", "btn.readings", "btn.transits", "btn.daily",
    "btn.profile", "btn.history", "btn.help", "btn.language", "btn.invite",
)
```

Add `"btn.gift"`:

```python
MENU_BUTTON_KEYS = (
    "btn.generate", "btn.ask", "btn.readings", "btn.transits", "btn.daily",
    "btn.profile", "btn.history", "btn.help", "btn.language", "btn.invite",
    "btn.gift",
)
```

- [ ] **Step 6: Add `btn.gift` to `main_menu_kb`**

In `src/quantuum/bot/ui/keyboards.py`, find the `main_menu_kb` factory. Locate the existing `_add(await i18n("btn.invite"))` call gated on `flags.get("referrals", True)` and add an analogous row just after it:

```python
if flags.get("gifts", True):
    _add(await i18n("btn.gift"))
```

- [ ] **Step 7: Write the gift handler module**

```python
# src/quantuum/bot/handlers/gift.py
from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from quantuum.bot.ui import text
from quantuum.bot.ui.callbacks import GiftCreateCb  # added in callbacks.py below
from quantuum.db.models import Account, AccountBalance, TenantBot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.gifts import (
    InsufficientCreditsError,
    MAX_GIFT_AMOUNT,
    MIN_GIFT_AMOUNT,
    create_gift,
    list_recent_gifts,
    sweep_expired_gifts,
)
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator

router = Router()

_GIFT_LABELS = text.menu_button_labels("btn.gift")


class Gift(StatesGroup):
    awaiting_amount = State()


async def _tenant_bot_username(session, tenant_id: int) -> str | None:
    row = (
        await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant_id))
    ).scalars().first()
    return row.bot_username if row else None


async def _render_history_lines(session, *, account_id: int, i18n: Translator) -> list[str]:
    rows = await list_recent_gifts(session, sender_account_id=account_id)
    if not rows:
        return [await i18n("gift.history_empty")]
    out: list[str] = []
    for r in rows:
        status_label = await i18n(f"gift.status.{r.status}", default=r.status)
        out.append(await i18n(
            "gift.history_row",
            date=r.created_at.strftime("%d.%m"),
            amount=r.amount,
            status=status_label,
        ))
    return out


async def show_gift_screen(
    message: Message, *, account_id: int, tenant_id: int, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, tenant_id, "gifts"):
            await message.answer(await i18n("gift.disabled"))
            return

        await sweep_expired_gifts(session, sender_account_id=account_id)
        bal = await session.get(AccountBalance, account_id)
        balance = bal.package_credits if bal else 0
        history_lines = await _render_history_lines(
            session, account_id=account_id, i18n=i18n
        )
        await session.commit()

    body_parts = [
        await i18n("gift.title"),
        "",
        await i18n("gift.balance_line", balance=balance),
        "",
        await i18n("gift.history_title"),
        *history_lines,
    ]
    builder = InlineKeyboardBuilder()
    builder.button(
        text=await i18n("gift.btn.create_new"),
        callback_data=GiftCreateCb(action="start").pack(),
    )
    builder.adjust(1)
    await message.answer("\n".join(body_parts), reply_markup=builder.as_markup())


@router.message(Command("gift"))
async def on_gift_cmd(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_gift_screen(
        message, account_id=account.id, tenant_id=tenant_id, i18n=i18n
    )


@router.message(F.text.in_(_GIFT_LABELS))
async def on_gift_btn(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_gift_screen(
        message, account_id=account.id, tenant_id=tenant_id, i18n=i18n
    )


@router.callback_query(GiftCreateCb.filter(F.action == "start"))
async def on_gift_create(
    query: CallbackQuery,
    callback_data: GiftCreateCb,
    state: FSMContext,
    account: Account,
    tenant_id: int,
    i18n: Translator,
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, tenant_id, "gifts"):
            await query.answer(await i18n("gift.disabled"), show_alert=True)
            return
        bal = await session.get(AccountBalance, account.id)
        balance = bal.package_credits if bal else 0
    if balance < MIN_GIFT_AMOUNT:
        await query.message.answer(await i18n("gift.no_balance"))
        await query.answer()
        return
    max_amount = min(balance, MAX_GIFT_AMOUNT)
    await state.set_state(Gift.awaiting_amount)
    await state.update_data(
        account_id=account.id, tenant_id=tenant_id, max_amount=max_amount
    )
    await query.message.answer(
        await i18n("gift.amount_prompt", max=max_amount)
        + "\n"
        + await i18n("gift.cancel_hint")
    )
    await query.answer()


@router.message(Command("cancel"), Gift.awaiting_amount)
async def on_gift_cancel(
    message: Message, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await message.answer(await i18n("gift.cancel_hint"))


@router.message(Gift.awaiting_amount)
async def on_amount_received(
    message: Message,
    state: FSMContext,
    account: Account,
    tenant_id: int,
    i18n: Translator,
) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    try:
        amount = int(raw)
    except ValueError:
        await message.answer(await i18n("gift.not_a_number"))
        return

    if amount < MIN_GIFT_AMOUNT:
        await message.answer(await i18n("gift.too_small"))
        return
    max_amount = data.get("max_amount", MAX_GIFT_AMOUNT)
    if amount > max_amount:
        await message.answer(await i18n("gift.too_large", max=max_amount))
        return

    async with get_sessionmaker()() as session:
        try:
            token = await create_gift(
                session,
                sender_account_id=account.id,
                tenant_id=tenant_id,
                amount=amount,
            )
        except InsufficientCreditsError:
            await session.rollback()
            await message.answer(await i18n("gift.no_balance"))
            await state.clear()
            return
        username = await _tenant_bot_username(session, tenant_id)
        await session.commit()

    if not username:
        await message.answer(await i18n("gift.disabled"))
        await state.clear()
        return

    link = f"https://t.me/{username}?start={token.code}"
    share_text = await i18n("gift.share_text")
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await i18n("gift.btn.create_new"), url=share_url)]
        ]
    )
    body = await i18n("gift.created", amount=amount, link=link)
    await message.answer(body, reply_markup=kb)
    await state.clear()
```

- [ ] **Step 8: Define `GiftCreateCb`**

In `src/quantuum/bot/ui/callbacks.py`, add near the other CallbackData classes:

```python
class GiftCreateCb(CallbackData, prefix="gcre"):
    action: str  # "start"
```

- [ ] **Step 9: Wire the router**

In `src/quantuum/bot/app.py`, add `gift` next to the existing `invite` import and include the router in the dispatcher chain (mirror the SP4 wiring).

- [ ] **Step 10: Remove the skip on the flag-off dispatcher test**

In `tests/test_start_token_dispatcher.py`, find `test_dispatch_gift_feature_flag_off_silent` and remove its `@pytest.mark.skip(...)` decorator.

- [ ] **Step 11: Run targeted tests until green**

```
uv run pytest tests/test_gift_handler.py tests/test_tenant_features_domain.py \
              tests/test_start_token_dispatcher.py -v
```

Expected: all PASS.

- [ ] **Step 12: Ruff check**

```
uv run ruff check src/quantuum/bot/handlers/gift.py \
                  src/quantuum/bot/ui/callbacks.py \
                  src/quantuum/bot/ui/keyboards.py \
                  src/quantuum/bot/ui/text.py \
                  src/quantuum/bot/app.py \
                  src/quantuum/domain/tenant_features.py \
                  tests/test_gift_handler.py
```

Expected: no issues.

- [ ] **Step 13: Commit**

```
git add src/quantuum/bot/handlers/gift.py \
        src/quantuum/bot/ui/callbacks.py \
        src/quantuum/bot/ui/keyboards.py \
        src/quantuum/bot/ui/text.py \
        src/quantuum/bot/app.py \
        src/quantuum/domain/tenant_features.py \
        tests/test_gift_handler.py \
        tests/test_tenant_features_domain.py \
        tests/test_start_token_dispatcher.py
git commit -m "feat(sp5-t5): /gift handler + menu button + gifts feature flag"
```

---

## Task 6 — Owner console Gifts submenu

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_console.py` — `OwnerGifts` FSM, `_gifts_keyboard`, 5 handlers, `Gifts` button on `/manage`
- Modify: `src/quantuum/bot/ui/callbacks.py` — `OwnerGiftsCb`
- Create: `tests/test_owner_gifts.py`

**Context:** Mirror SP3 Branding / SP4 Referrals. All handlers take `query: CallbackQuery, callback_data: OwnerGiftsCb, i18n: Translator` (+ `state` where relevant), extract `tg_user_id = str(query.from_user.id)`, call `await authorize_tenant_action(session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id)`, and return early showing `owner.no_rights` on `None`. The FSM state stores `tenant_id`; the value-text handler re-authorises with `message.from_user.id`.

- [ ] **Step 1: Add `OwnerGiftsCb` to `src/quantuum/bot/ui/callbacks.py`**

```python
class OwnerGiftsCb(CallbackData, prefix="ogft"):
    action: str  # "open" | "edit" | "reset" | "cancel"
    tenant_id: int = 0
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_owner_gifts.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import (
    OwnerGifts,
    on_gifts_cancel,
    on_gifts_edit,
    on_gifts_open,
    on_gifts_reset,
    on_gifts_value,
)
from quantuum.bot.ui.callbacks import OwnerGiftsCb
from quantuum.db.models import TenantRole
from quantuum.domain.gifts import (
    DEFAULT_EXPIRY_DAYS,
    MAX_EXPIRY_DAYS,
    MIN_EXPIRY_DAYS,
    get_expiry_days,
)


async def _seed_owner(session, t_id, tg=42):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t_id, tg_user_id=str(tg)
    )
    session.add(TenantRole(tenant_id=t_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _query(tg_id: int):
    q = MagicMock()
    q.from_user = MagicMock(id=tg_id)
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    q.answer = AsyncMock()
    return q


def _make_state(tg_id: int) -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id))


async def test_open_shows_current_value(session, default_tenant):
    await _seed_owner(session, default_tenant.id)
    q = _query(42)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}:{kw}>")
    await on_gifts_open(
        q,
        callback_data=OwnerGiftsCb(action="open", tenant_id=default_tenant.id),
        i18n=i18n,
    )
    body = q.message.answer.await_args.args[0]
    assert "owner.gifts.title" in body
    assert f"value': {DEFAULT_EXPIRY_DAYS}" in body  # placeholder render in mock


async def test_open_rejects_non_owner(session, default_tenant):
    # No TenantRole seeded → authorize returns None.
    q = _query(99)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")
    await on_gifts_open(
        q,
        callback_data=OwnerGiftsCb(action="open", tenant_id=default_tenant.id),
        i18n=i18n,
    )
    q.answer.assert_awaited()
    args, kwargs = q.answer.await_args
    assert kwargs.get("show_alert") is True


async def test_edit_sets_fsm_state(session, default_tenant):
    await _seed_owner(session, default_tenant.id)
    q = _query(42)
    state = _make_state(42)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")
    await on_gifts_edit(
        q,
        callback_data=OwnerGiftsCb(action="edit", tenant_id=default_tenant.id),
        state=state,
        i18n=i18n,
    )
    assert await state.get_state() == OwnerGifts.awaiting_value.state
    data = await state.get_data()
    assert data["tenant_id"] == default_tenant.id


async def test_value_happy_path_saves(session, default_tenant):
    await _seed_owner(session, default_tenant.id)
    msg = MagicMock()
    msg.text = "14"
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    state = _make_state(42)
    await state.update_data(tenant_id=default_tenant.id)
    await state.set_state(OwnerGifts.awaiting_value)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")

    await on_gifts_value(msg, state=state, i18n=i18n)

    # Re-read via a fresh session because the handler opens its own.
    from quantuum.db.session import get_sessionmaker
    async with get_sessionmaker()() as s2:
        assert await get_expiry_days(s2, tenant_id=default_tenant.id) == 14
    msg.answer.assert_awaited_with("<owner.gifts.saved>")
    assert await state.get_state() is None


@pytest.mark.parametrize("raw, key", [
    ("abc", "owner.gifts.not_a_number"),
    (str(MIN_EXPIRY_DAYS - 1), "owner.gifts.too_small"),
    (str(MAX_EXPIRY_DAYS + 1), "owner.gifts.too_large"),
])
async def test_value_validation_errors(session, default_tenant, raw, key):
    await _seed_owner(session, default_tenant.id)
    msg = MagicMock()
    msg.text = raw
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    state = _make_state(42)
    await state.update_data(tenant_id=default_tenant.id)
    await state.set_state(OwnerGifts.awaiting_value)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    await on_gifts_value(msg, state=state, i18n=i18n)
    msg.answer.assert_awaited()
    body = msg.answer.await_args.args[0]
    assert key in body
    assert await state.get_state() == OwnerGifts.awaiting_value.state  # still in FSM


async def test_reset_restores_default(session, default_tenant):
    owner = await _seed_owner(session, default_tenant.id)
    from quantuum.domain.gifts import set_expiry_days
    from quantuum.db.session import get_sessionmaker

    async with get_sessionmaker()() as s2:
        await set_expiry_days(
            s2, tenant_id=default_tenant.id, days=90, by_account_id=owner.id
        )
        await s2.commit()

    q = _query(42)
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")
    await on_gifts_reset(
        q,
        callback_data=OwnerGiftsCb(action="reset", tenant_id=default_tenant.id),
        i18n=i18n,
    )

    async with get_sessionmaker()() as s3:
        assert await get_expiry_days(s3, tenant_id=default_tenant.id) == DEFAULT_EXPIRY_DAYS
    q.message.answer.assert_awaited_with("<owner.gifts.reset>")


async def test_cancel_exits_fsm(session, default_tenant):
    msg = MagicMock()
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    state = _make_state(42)
    await state.set_state(OwnerGifts.awaiting_value)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    await on_gifts_cancel(msg, state=state, i18n=i18n)
    assert await state.get_state() is None
```

- [ ] **Step 3: Run the failing test**

```
uv run pytest tests/test_owner_gifts.py -v
```

Expected: ImportError on `OwnerGifts`/`on_gifts_open` (handler not yet written).

- [ ] **Step 4: Implement the owner submenu**

In `src/quantuum/bot/handlers/owner_console.py`:

1. Import:

```python
from quantuum.bot.ui.callbacks import (
    OwnerBrandingCb, OwnerFeatureCb, OwnerGiftsCb, OwnerManageCb,
    OwnerReferralsCb, OwnerUserCb,
)
from quantuum.domain.gifts import (
    DEFAULT_EXPIRY_DAYS,
    MAX_EXPIRY_DAYS,
    MIN_EXPIRY_DAYS,
    get_expiry_days,
    reset_expiry_days,
    set_expiry_days,
)
```

2. Add a `Gifts` button to the `/manage` keyboard, just after the Referrals row (`src/quantuum/bot/handlers/owner_console.py:113-120`):

```python
builder.row(
    InlineKeyboardButton(
        text=await i18n("owner.gifts.menu_button"),
        callback_data=OwnerGiftsCb(action="open", tenant_id=tenant.id).pack(),
    )
)
```

3. Add the submenu, FSM, and handlers at the bottom of the file (after the SP4 referrals block):

```python
# ── SP5: Gifts submenu + edit FSM ───────────────────────────────────────────


class OwnerGifts(StatesGroup):
    awaiting_value = State()


async def _gifts_keyboard(i18n: Translator, tenant_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=await i18n("owner.gifts.menu_button"),
        callback_data=OwnerGiftsCb(action="edit", tenant_id=tenant_id).pack(),
    )
    b.button(
        text=await i18n("owner.gifts.reset"),
        callback_data=OwnerGiftsCb(action="reset", tenant_id=tenant_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()


@router.callback_query(OwnerGiftsCb.filter(F.action == "open"))
async def on_gifts_open(
    query: CallbackQuery,
    callback_data: OwnerGiftsCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        current = await get_expiry_days(session, tenant_id=callback_data.tenant_id)
    body = (
        f"{await i18n('owner.gifts.title')}\n\n"
        f"{await i18n('owner.gifts.current_value', value=current)}"
    )
    await query.message.answer(
        body, reply_markup=await _gifts_keyboard(i18n, callback_data.tenant_id)
    )
    await query.answer()


@router.callback_query(OwnerGiftsCb.filter(F.action == "edit"))
async def on_gifts_edit(
    query: CallbackQuery,
    callback_data: OwnerGiftsCb,
    state: FSMContext,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerGifts.awaiting_value)
    await state.update_data(tenant_id=callback_data.tenant_id)
    await query.message.answer(
        await i18n("owner.gifts.prompt", min=MIN_EXPIRY_DAYS, max=MAX_EXPIRY_DAYS)
        + "\n"
        + await i18n("owner.gifts.cancel_hint"),
    )
    await query.answer()


@router.callback_query(OwnerGiftsCb.filter(F.action == "reset"))
async def on_gifts_reset(
    query: CallbackQuery,
    callback_data: OwnerGiftsCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        await reset_expiry_days(
            session, tenant_id=callback_data.tenant_id, by_account_id=actor_id
        )
        await session.commit()
    await query.message.answer(await i18n("owner.gifts.reset"))
    await query.answer()


@router.message(Command("cancel"), OwnerGifts.awaiting_value)
async def on_gifts_cancel(
    message: Message, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await message.answer(await i18n("menu.cancelled"))


@router.message(OwnerGifts.awaiting_value)
async def on_gifts_value(
    message: Message,
    state: FSMContext,
    i18n: Translator,
) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    tg_user_id = str(message.from_user.id)

    raw = (message.text or "").strip()
    try:
        days = int(raw)
    except ValueError:
        await message.answer(await i18n("owner.gifts.not_a_number"))
        return
    if days < MIN_EXPIRY_DAYS:
        await message.answer(await i18n("owner.gifts.too_small", min=MIN_EXPIRY_DAYS))
        return
    if days > MAX_EXPIRY_DAYS:
        await message.answer(await i18n("owner.gifts.too_large", max=MAX_EXPIRY_DAYS))
        return

    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=tenant_id
        )
        if actor_id is None:
            await state.clear()
            await message.answer(await i18n("owner.no_rights"))
            return
        await set_expiry_days(
            session, tenant_id=tenant_id, days=days, by_account_id=actor_id
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.gifts.saved"))
```

- [ ] **Step 5: Run targeted tests until green**

```
uv run pytest tests/test_owner_gifts.py -v
```

Expected: all PASS.

- [ ] **Step 6: Ruff check**

```
uv run ruff check src/quantuum/bot/handlers/owner_console.py \
                  src/quantuum/bot/ui/callbacks.py \
                  tests/test_owner_gifts.py
```

Expected: no issues.

- [ ] **Step 7: Commit**

```
git add src/quantuum/bot/handlers/owner_console.py \
        src/quantuum/bot/ui/callbacks.py \
        tests/test_owner_gifts.py
git commit -m "feat(sp5-t6): owner console Gifts submenu + FSM"
```

---

## Task 7 — Full suite + ruff gate

**Files:**
- All SP5-touched files (final sweep)

**Context:** SP4 stage end ran the full suite and confirmed 1376 tests pass. SP5 should add ~80 tests (T1: 2; T2: ~14; T3: 5 new; T4: ~370 parametrized i18n; T5: 5; T6: 8). Final expectation: ~1456+ tests pass, ruff clean on SP5 files.

- [ ] **Step 1: Run the full suite**

```
uv run pytest tests/ -v --tb=short
```

Expected: 0 failures. Common late-breaking issues to anticipate:
- Pre-existing menu-keyboard tests asserting the count of menu buttons — update them to include `btn.gift` (SP4 hit a similar issue with `btn.invite`).
- `test_tenant_features_domain.py` — already bumped to 14 in T5; verify.
- Any test that hardcoded `len(MENU_BUTTON_KEYS)` — bump.

For each failure, prefer fixing the assertion (SP5 added a new menu button / feature, so the inventory has changed) over reverting SP5 changes.

- [ ] **Step 2: Ruff check on all SP5 files**

```
uv run ruff check \
    src/quantuum/domain/gifts.py \
    src/quantuum/domain/tenant_features.py \
    src/quantuum/bot/handlers/gift.py \
    src/quantuum/bot/handlers/start_tokens.py \
    src/quantuum/bot/handlers/start.py \
    src/quantuum/bot/handlers/owner_console.py \
    src/quantuum/bot/ui/callbacks.py \
    src/quantuum/bot/ui/text.py \
    src/quantuum/bot/ui/keyboards.py \
    src/quantuum/bot/app.py \
    src/quantuum/db/models.py \
    src/quantuum/i18n/seed_strings.py \
    src/quantuum/i18n/translations/de.py \
    src/quantuum/i18n/translations/es.py \
    src/quantuum/i18n/translations/fr.py \
    src/quantuum/i18n/translations/hi.py \
    src/quantuum/i18n/translations/it.py \
    src/quantuum/i18n/translations/pt.py \
    src/quantuum/i18n/translations/tr.py \
    src/quantuum/i18n/translations/zh.py \
    tests/test_gift_domain.py \
    tests/test_gift_handler.py \
    tests/test_gift_i18n.py \
    tests/test_owner_gifts.py \
    tests/test_start_token_uses_no_unique.py
```

Expected: no issues on SP5 files. SP4 final stage skipped pre-existing ruff findings in unrelated files; do the same here — fix only SP5-touched findings.

- [ ] **Step 3: If the suite is green and ruff is clean, commit any incidental fixes**

```
git status
# if non-empty:
git add <files>
git commit -m "fix(sp5-t7): full-suite/ruff fixups"
```

If nothing changed, skip the commit.

- [ ] **Step 4: Report**

Print the commit chain since `main`'s SP5 starting point:

```
git log --oneline 9eb2e3e..HEAD
```

End the SP5 stage with:
- total commits in SP5 chain
- pass/fail count from full suite
- any open follow-ups (Section 8 of the spec)

---

## Self-review notes (run after writing — done inline)

- **Spec coverage:** every section in the spec maps to a task (4.1 model + 4.2 schema → T1; 4.3 + 4.5 → T2; 4.6 → T3; 4.7 + 4.4 flag → T5; 4.8 → T6; 4.9 i18n → T4; 4.10 audit → covered inside T2/T3/T6).
- **Placeholder scan:** no "TBD" or "similar to Task N". Every code step contains code. Every test step contains tests.
- **Type consistency:** `GiftClaimResult` defined in T3, referenced in T3 test and T3 `/start` mod. `InsufficientCreditsError` defined in T2, referenced in T2 tests and T5 handler. `GiftCreateCb` declared in T5 step 8 before the file in step 7 imports it (engineer should do step 8 first; clarified by ordering in the diff log). `OwnerGifts`, `OwnerGiftsCb` declared in T6 step 1 (callback) and T6 step 4 (FSM + handlers).
- **Schema check:** dropping the UNIQUE in T1 unblocks SP4 referrals + future SP5 gifts; SP4 referral handler's pre-flight SELECT (verified at `src/quantuum/bot/handlers/start_tokens.py:71-75`) means no behavioural regression.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-28-gift-a-friend.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec opus + code sonnet), per-task targeted tests during execution. Matches SP4 cadence.
2. **Inline Execution** — execute tasks in this session with batch checkpoints.

Which approach?
