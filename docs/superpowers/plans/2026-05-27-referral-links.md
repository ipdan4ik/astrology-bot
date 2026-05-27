# Referral Links Implementation Plan (SP4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tenant-bot customers can share a Telegram deep link that brings new users to the same bot. First time the new user pays AND spends ≥1 package_credit, the referrer's `package_credits` gets bumped by `referral_reward_credits` (per-tenant config, default 10, range 0-1000).

**Architecture:** Two new tables. `start_tokens` is a generic typed deep-link table (kind = `referral` for SP4; future kinds plug in via a dispatcher). `start_token_uses` is the attribution ledger with `UNIQUE(account_id)` enforcing one-token-per-account. New `domain/referrals.py` mirrors SP2/SP3 domain shape. `/start <payload>` parses + dispatches by `kind`. Payout is called at the tail of `consume_quota` when `charged_against == "package"`, gated on `EXISTS Payment(status='paid')`. Customer UX: `/invite` command + a new "Invite a friend" reply-keyboard button. Owner UX: `/owner_console` Referrals submenu with FSM edit flow that mirrors SP3 Branding.

**Tech Stack:** Python 3.13 (PEP 604 unions), SQLModel + Alembic, aiogram 3 FSM + CallbackData, pytest-asyncio (asyncio_mode=auto), structlog via `quantuum.logging_setup.get_logger`, ruff.

**Spec:** `docs/superpowers/specs/2026-05-27-referral-links-design.md`

---

## File Structure

**Create:**
- `alembic/versions/<rev>_start_tokens.py` — Alembic migration for both tables.
- `src/quantuum/domain/referrals.py` — generate_referral_code, get_referral_stats, maybe_payout_referral, get_reward_credits, set_reward_credits, reset_reward_credits.
- `src/quantuum/bot/handlers/start_tokens.py` — `parse_start_payload`, `resolve_start_token`, `dispatch_start_token`, `handle_referral_token`.
- `src/quantuum/bot/handlers/invite.py` — `/invite` command, menu button callback, `show_invite`.
- `tests/test_referral_domain.py` — domain helpers, payout edge cases.
- `tests/test_start_token_dispatcher.py` — payload parsing, kind dispatcher, referral handler, self-referral, already-attributed, expired, disabled, maxed.
- `tests/test_referral_i18n.py` — all 16 keys × 10 locales seeded.
- `tests/test_invite_handler.py` — /invite command, menu button, disabled tenant, share-URL button rendering, stats.
- `tests/test_owner_referrals.py` — owner submenu, FSM edit, validation, reset, AuditLog write.
- `tests/test_consume_quota_referral_integration.py` — end-to-end: paid+spend triggers payout once.

**Modify:**
- `src/quantuum/db/models.py` — add `StartToken` and `StartTokenUse` SQLModel classes.
- `src/quantuum/domain/quota.py` — call `maybe_payout_referral` at end of `consume_quota` when `charged_against == "package"`.
- `src/quantuum/domain/tenant_features.py` — append `"referrals"` to `FEATURE_KEYS`.
- `src/quantuum/bot/handlers/start.py` — parse + dispatch start-token payload before the welcome flow.
- `src/quantuum/bot/handlers/menu.py` — add Invite reply-button + `on_invite_btn` handler.
- `src/quantuum/bot/ui/keyboards.py` — append Invite button to `main_menu_kb` when `referrals` feature enabled.
- `src/quantuum/bot/ui/text.py` — register `btn.invite` in `menu_button_labels` source.
- `src/quantuum/bot/handlers/owner_console.py` — Referrals button on `/manage`, submenu, FSM edit flow.
- `src/quantuum/bot/ui/callbacks.py` — add `OwnerReferralsCb` CallbackData.
- `src/quantuum/i18n/seed_strings.py` — append 16 keys (ru+en + new `btn.invite`).
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — append same 16 keys.

---

## Task 1: Migration + models (`start_tokens`, `start_token_uses`)

**Files:**
- Modify: `src/quantuum/db/models.py` (append at end)
- Create: `alembic/versions/<rev>_start_tokens.py`
- Test: `tests/test_referral_domain.py` (first failing import test)

- [ ] **Step 1: Determine current alembic head**

Run: `uv run alembic heads`
Note the printed head revision. Use it as `down_revision` in the new migration. The new revision id is `e1f2a3b4c5d6` (12-hex). If that ID is already taken, increment the last hex digit until free.

- [ ] **Step 2: Append models to `src/quantuum/db/models.py`**

Add after the last existing table class:

```python
class StartToken(SQLModel, table=True):
    __tablename__ = "start_tokens"

    code: str = Field(primary_key=True, max_length=64)
    kind: str = Field(index=True)  # referral | discount | promo | ...
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    owner_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    payload: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}")
    )
    status: str = "active"  # active | disabled
    max_uses: int | None = Field(default=None)
    used_count: int = 0
    expires_at: datetime | None = _dt_field(default=None)
    created_at: datetime = _dt_field(default_factory=utcnow)


class StartTokenUse(SQLModel, table=True):
    __tablename__ = "start_token_uses"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_start_token_uses_account_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    token_code: str = Field(foreign_key="start_tokens.code", index=True)
    account_id: int = Field(foreign_key="accounts.id")
    used_at: datetime = _dt_field(default_factory=utcnow)
    claimed_at: datetime | None = _dt_field(default=None)
```

Ensure `UniqueConstraint` and `Column`, `JSONB` are imported at the top of the file (they're already imported for other tables).

- [ ] **Step 3: Generate migration**

```bash
uv run alembic revision -m start_tokens --rev-id e1f2a3b4c5d6
```

Edit the produced file to set `down_revision` to whatever Step 1 reported. Replace the empty `upgrade()` / `downgrade()` bodies with:

```python
def upgrade() -> None:
    op.create_table(
        "start_tokens",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner_account_id", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["owner_account_id"], ["accounts.id"]),
    )
    op.create_index("ix_start_tokens_kind", "start_tokens", ["kind"])
    op.create_index("ix_start_tokens_tenant_id", "start_tokens", ["tenant_id"])
    op.create_index(
        "ix_start_tokens_owner_account_id",
        "start_tokens",
        ["owner_account_id"],
    )

    op.create_table(
        "start_token_uses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_code", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["token_code"], ["start_tokens.code"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("account_id", name="uq_start_token_uses_account_id"),
    )
    op.create_index(
        "ix_start_token_uses_token_code", "start_token_uses", ["token_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_start_token_uses_token_code", table_name="start_token_uses")
    op.drop_table("start_token_uses")
    op.drop_index("ix_start_tokens_owner_account_id", table_name="start_tokens")
    op.drop_index("ix_start_tokens_tenant_id", table_name="start_tokens")
    op.drop_index("ix_start_tokens_kind", table_name="start_tokens")
    op.drop_table("start_tokens")
```

Ensure imports at top: `import sqlalchemy as sa`, `from alembic import op`, `from sqlalchemy.dialects import postgresql`.

- [ ] **Step 4: Apply migration against test DB**

```bash
uv run alembic upgrade head
```

Expected: "Running upgrade <prev> -> e1f2a3b4c5d6, start_tokens" with no errors.

- [ ] **Step 5: Write a smoke test for the new models**

Create `tests/test_referral_domain.py` with one initial import-smoke test:

```python
import pytest

from quantuum.db.models import StartToken, StartTokenUse


def test_models_importable():
    assert StartToken.__tablename__ == "start_tokens"
    assert StartTokenUse.__tablename__ == "start_token_uses"
```

- [ ] **Step 6: Run the smoke test**

```bash
uv run pytest tests/test_referral_domain.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/e1f2a3b4c5d6_start_tokens.py tests/test_referral_domain.py
git commit -m "feat(sp4): start_tokens + start_token_uses tables"
```

---

## Task 2: Domain layer (`domain/referrals.py`)

**Files:**
- Create: `src/quantuum/domain/referrals.py`
- Test: `tests/test_referral_domain.py` (extend with full coverage)

Mirror SP2 (`tenant_features.py`) and SP3 (`tenant_branding.py`) shape: explicit validation, `await session.flush()` at end of mutating ops, `AuditLog` writes via `domain/audit.py::record_audit`.

- [ ] **Step 1: Write failing test cases**

Append to `tests/test_referral_domain.py`:

```python
from datetime import timedelta

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AuditLog,
    Payment,
    PaymentProvider,
    StartToken,
    StartTokenUse,
    Tenant,
    TenantConfig,
)
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    MAX_REWARD_CREDITS,
    REFERRAL_KIND,
    REFERRAL_CODE_LENGTH,
    REFERRAL_REWARD_CONFIG_KEY,
    generate_referral_code,
    get_referral_stats,
    get_reward_credits,
    maybe_payout_referral,
    reset_reward_credits,
    set_reward_credits,
)


async def _make_tenant(session) -> Tenant:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    return t


async def _make_account(session, tenant_id: int, tg_id: int) -> int:
    acct = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_id=tg_id, username=f"u{tg_id}"
    )
    return acct.id


async def _mark_paid(session, *, tenant_id: int, account_id: int) -> Payment:
    p = Payment(
        tenant_id=tenant_id,
        account_id=account_id,
        amount_cents=100,
        status="paid",
        paid_at=utcnow(),
    )
    session.add(p)
    await session.flush()
    return p


async def test_generate_referral_code_creates_token(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)

    assert isinstance(code, str)
    assert len(code) == REFERRAL_CODE_LENGTH
    row = await session.get(StartToken, code)
    assert row is not None
    assert row.kind == REFERRAL_KIND
    assert row.owner_account_id == aid
    assert row.tenant_id == t.id
    assert row.max_uses is None
    assert row.expires_at is None
    assert row.status == "active"


async def test_generate_referral_code_idempotent(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    code1 = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    code2 = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    assert code1 == code2


async def test_generate_referral_code_writes_audit(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    rows = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "referral.code_created")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].tenant_id == t.id
    assert rows[0].actor_account_id == aid


async def test_get_referral_stats_zero(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    stats = await get_referral_stats(session, account_id=aid)
    assert stats == {"code": None, "claimed": 0, "pending": 0}


async def test_get_referral_stats_counts(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)

    # one claimed, one pending
    ref1 = await _make_account(session, t.id, 2001)
    ref2 = await _make_account(session, t.id, 2002)
    session.add(StartTokenUse(token_code=code, account_id=ref1, claimed_at=utcnow()))
    session.add(StartTokenUse(token_code=code, account_id=ref2))
    await session.flush()

    stats = await get_referral_stats(session, account_id=referrer)
    assert stats == {"code": code, "claimed": 1, "pending": 1}


async def test_get_reward_credits_default(session: AsyncSession):
    t = await _make_tenant(session)
    assert await get_reward_credits(session, tenant_id=t.id) == DEFAULT_REWARD_CREDITS


async def test_set_reward_credits_upsert(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 9001)
    await set_reward_credits(session, tenant_id=t.id, value=25, by_account_id=aid)
    assert await get_reward_credits(session, tenant_id=t.id) == 25
    await set_reward_credits(session, tenant_id=t.id, value=50, by_account_id=aid)
    assert await get_reward_credits(session, tenant_id=t.id) == 50


async def test_set_reward_credits_validates_range(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 9001)
    with pytest.raises(ValueError):
        await set_reward_credits(session, tenant_id=t.id, value=-1, by_account_id=aid)
    with pytest.raises(ValueError):
        await set_reward_credits(
            session, tenant_id=t.id, value=MAX_REWARD_CREDITS + 1, by_account_id=aid
        )


async def test_reset_reward_credits_idempotent(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 9001)
    await set_reward_credits(session, tenant_id=t.id, value=25, by_account_id=aid)
    await reset_reward_credits(session, tenant_id=t.id, by_account_id=aid)
    await reset_reward_credits(session, tenant_id=t.id, by_account_id=aid)
    assert await get_reward_credits(session, tenant_id=t.id) == DEFAULT_REWARD_CREDITS


async def test_maybe_payout_referral_no_use_row(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 5001)
    fired = await maybe_payout_referral(session, referee_account_id=aid)
    assert fired is False


async def test_maybe_payout_referral_no_payment(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is False


async def test_maybe_payout_referral_happy_path(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    session.add(AccountBalance(account_id=referrer, package_credits=0))
    await _mark_paid(session, tenant_id=t.id, account_id=referee)
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is True

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS

    use = (
        (await session.execute(select(StartTokenUse).where(StartTokenUse.account_id == referee)))
        .scalars()
        .one()
    )
    assert use.claimed_at is not None

    audit_rows = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "referral.payout")))
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1


async def test_maybe_payout_referral_one_shot(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    session.add(AccountBalance(account_id=referrer, package_credits=0))
    await _mark_paid(session, tenant_id=t.id, account_id=referee)
    await session.flush()

    await maybe_payout_referral(session, referee_account_id=referee)
    await maybe_payout_referral(session, referee_account_id=referee)

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS  # exactly one bump


async def test_maybe_payout_referral_zero_reward_closes_loop(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    by = await _make_account(session, t.id, 9001)
    await set_reward_credits(session, tenant_id=t.id, value=0, by_account_id=by)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    session.add(AccountBalance(account_id=referrer, package_credits=0))
    await _mark_paid(session, tenant_id=t.id, account_id=referee)
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is True
    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == 0
    use = (
        (await session.execute(select(StartTokenUse).where(StartTokenUse.account_id == referee)))
        .scalars()
        .one()
    )
    assert use.claimed_at is not None  # loop closed
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_referral_domain.py -v
```

Expected: ImportError (module not yet created).

- [ ] **Step 3: Implement `src/quantuum/domain/referrals.py`**

```python
import secrets
import string

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    Payment,
    StartToken,
    StartTokenUse,
    TenantConfig,
)
from quantuum.domain.accounts import adjust_package_credits
from quantuum.domain.audit import record_audit
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

REFERRAL_KIND = "referral"
REFERRAL_CODE_LENGTH = 8
REFERRAL_REWARD_CONFIG_KEY = "referral.reward_credits"
DEFAULT_REWARD_CREDITS = 10
MAX_REWARD_CREDITS = 1000

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_GEN_MAX_RETRIES = 5


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


async def generate_referral_code(
    session: AsyncSession, *, account_id: int, tenant_id: int
) -> str:
    """Return the referral code owned by ``account_id``, creating one if absent."""
    existing = (
        await session.execute(
            select(StartToken).where(
                StartToken.kind == REFERRAL_KIND,
                StartToken.owner_account_id == account_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing.code

    for _ in range(_GEN_MAX_RETRIES):
        code = _gen_code()
        if (await session.get(StartToken, code)) is None:
            token = StartToken(
                code=code,
                kind=REFERRAL_KIND,
                tenant_id=tenant_id,
                owner_account_id=account_id,
                status="active",
            )
            session.add(token)
            await session.flush()
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_account_id=account_id,
                action="referral.code_created",
                entity_type="start_token",
                entity_id=code,
                payload={"code": code},
            )
            return code
    raise RuntimeError("could not generate unique referral code after retries")


async def get_referral_stats(
    session: AsyncSession, *, account_id: int
) -> dict[str, int | str | None]:
    """Return {code, claimed, pending} for the account's referral code."""
    token = (
        await session.execute(
            select(StartToken).where(
                StartToken.kind == REFERRAL_KIND,
                StartToken.owner_account_id == account_id,
            )
        )
    ).scalars().first()
    if token is None:
        return {"code": None, "claimed": 0, "pending": 0}

    rows = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.token_code == token.code)
        )
    ).scalars().all()
    claimed = sum(1 for r in rows if r.claimed_at is not None)
    pending = sum(1 for r in rows if r.claimed_at is None)
    return {"code": token.code, "claimed": claimed, "pending": pending}


async def get_reward_credits(session: AsyncSession, *, tenant_id: int) -> int:
    row = await session.get(TenantConfig, (tenant_id, REFERRAL_REWARD_CONFIG_KEY))
    if row is None:
        return DEFAULT_REWARD_CREDITS
    value = row.value_jsonb.get("value")
    if not isinstance(value, int):
        return DEFAULT_REWARD_CREDITS
    return value


async def set_reward_credits(
    session: AsyncSession,
    *,
    tenant_id: int,
    value: int,
    by_account_id: int,
) -> None:
    if not isinstance(value, int) or value < 0 or value > MAX_REWARD_CREDITS:
        raise ValueError(f"value must be int in [0, {MAX_REWARD_CREDITS}], got {value!r}")
    old = await get_reward_credits(session, tenant_id=tenant_id)
    row = await session.get(TenantConfig, (tenant_id, REFERRAL_REWARD_CONFIG_KEY))
    if row is None:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=REFERRAL_REWARD_CONFIG_KEY,
            value_jsonb={"value": value},
            updated_by_account_id=by_account_id,
        )
        session.add(row)
    else:
        row.value_jsonb = {"value": value}
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="referral.config_set",
        entity_type="tenant_config",
        entity_id=REFERRAL_REWARD_CONFIG_KEY,
        payload={"old": old, "new": value},
    )


async def reset_reward_credits(
    session: AsyncSession, *, tenant_id: int, by_account_id: int
) -> None:
    row = await session.get(TenantConfig, (tenant_id, REFERRAL_REWARD_CONFIG_KEY))
    if row is None:
        return
    old = row.value_jsonb.get("value", DEFAULT_REWARD_CREDITS)
    await session.delete(row)
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="referral.config_set",
        entity_type="tenant_config",
        entity_id=REFERRAL_REWARD_CONFIG_KEY,
        payload={"old": old, "new": DEFAULT_REWARD_CREDITS, "reset": True},
    )


async def maybe_payout_referral(
    session: AsyncSession, *, referee_account_id: int
) -> bool:
    """Fire the referrer payout when referee has both a paid Payment and an
    unclaimed attribution. Returns True iff a use row was just closed.

    Caller must wrap in try/except — payout errors must not roll back the
    spend that triggered us.
    """
    use = (
        await session.execute(
            select(StartTokenUse).where(
                StartTokenUse.account_id == referee_account_id,
                StartTokenUse.claimed_at.is_(None),
            )
        )
    ).scalars().first()
    if use is None:
        return False

    token = await session.get(StartToken, use.token_code)
    if token is None or token.kind != REFERRAL_KIND or token.owner_account_id is None:
        return False

    has_paid = (
        await session.execute(
            select(
                exists().where(
                    Payment.account_id == referee_account_id,
                    Payment.status == "paid",
                )
            )
        )
    ).scalar()
    if not has_paid:
        return False

    amount = await get_reward_credits(session, tenant_id=token.tenant_id)
    if amount > 0:
        await adjust_package_credits(session, token.owner_account_id, amount)
    use.claimed_at = utcnow()
    session.add(use)
    await session.flush()
    await record_audit(
        session,
        tenant_id=token.tenant_id,
        actor_account_id=token.owner_account_id,
        action="referral.payout",
        entity_type="start_token_use",
        entity_id=use.id,
        payload={
            "referee_id": referee_account_id,
            "referrer_id": token.owner_account_id,
            "amount": amount,
            "code": token.code,
        },
    )
    return True
```

- [ ] **Step 4: Run domain tests, confirm green**

```bash
uv run pytest tests/test_referral_domain.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Ruff sweep**

```bash
uv run ruff check src/quantuum/domain/referrals.py tests/test_referral_domain.py
```

Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/referrals.py tests/test_referral_domain.py
git commit -m "feat(sp4): domain layer (generate/stats/payout/reward config)"
```

---

## Task 3: i18n seed — 16 referral keys × 10 languages

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Modify: `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`
- Create: `tests/test_referral_i18n.py`

Same shape as SP3 Task 2 — append to BASE_STRINGS ru+en, then mirror across 8 locale modules.

- [ ] **Step 1: Write the failing coverage test**

Create `tests/test_referral_i18n.py`:

```python
import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

REFERRAL_I18N_KEYS = (
    "btn.invite",
    "invite.title",
    "invite.link_label",
    "invite.earned",
    "invite.share_text",
    "invite.disabled",
    "invite.unknown_code",
    "owner.referrals.title",
    "owner.referrals.current_value",
    "owner.referrals.prompt",
    "owner.referrals.saved",
    "owner.referrals.reset",
    "owner.referrals.too_large",
    "owner.referrals.not_a_number",
    "owner.referrals.cancel_hint",
    "owner.referrals.menu_button",
)

LOCALE_MODULES = {
    "de": de,
    "es": es,
    "fr": fr,
    "hi": hi,
    "it": it,
    "pt": pt,
    "tr": tr,
    "zh": zh,
}


@pytest.mark.parametrize("key", REFERRAL_I18N_KEYS)
def test_base_strings_has_ru_en(key: str):
    assert key in BASE_STRINGS, f"missing key {key} in BASE_STRINGS"
    assert "ru" in BASE_STRINGS[key]
    assert "en" in BASE_STRINGS[key]
    assert BASE_STRINGS[key]["ru"].strip()
    assert BASE_STRINGS[key]["en"].strip()


@pytest.mark.parametrize("lang,mod", LOCALE_MODULES.items())
@pytest.mark.parametrize("key", REFERRAL_I18N_KEYS)
def test_locale_module_has_key(key: str, lang: str, mod):
    assert hasattr(mod, "STRINGS"), f"{lang} module lacks STRINGS"
    assert key in mod.STRINGS, f"key {key} missing in {lang} module"
    assert mod.STRINGS[key].strip()


def test_invite_earned_uses_template_vars():
    assert "{credits}" in BASE_STRINGS["invite.earned"]["ru"]
    assert "{friends}" in BASE_STRINGS["invite.earned"]["ru"]


def test_owner_referrals_current_value_uses_template_var():
    assert "{value}" in BASE_STRINGS["owner.referrals.current_value"]["ru"]


def test_owner_referrals_prompt_uses_max_var():
    assert "{max}" in BASE_STRINGS["owner.referrals.prompt"]["ru"]
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_referral_i18n.py -v
```

Expected: KeyError / AttributeError on missing keys.

- [ ] **Step 3: Append to `BASE_STRINGS` in `src/quantuum/i18n/seed_strings.py`**

Append the following block to `BASE_STRINGS` (find the closing `}` of the dict and insert before it). Use the format `"key": {"ru": "...", "en": "..."},` consistent with SP3.

```python
    "btn.invite": {
        "ru": "🎁 Пригласить друга",
        "en": "🎁 Invite a friend",
    },
    "invite.title": {
        "ru": "Приглашайте друзей в этот бот.",
        "en": "Invite friends to this bot.",
    },
    "invite.link_label": {
        "ru": "Ваша ссылка",
        "en": "Your link",
    },
    "invite.earned": {
        "ru": "Заработано: {credits} кредитов от {friends} друзей.",
        "en": "Earned: {credits} credits from {friends} friends.",
    },
    "invite.share_text": {
        "ru": "Попробуй этого бота",
        "en": "Try this bot",
    },
    "invite.disabled": {
        "ru": "Реферальная программа в этом боте отключена.",
        "en": "Referrals are disabled in this bot.",
    },
    "invite.unknown_code": {
        "ru": "Реферальная ссылка не распознана. Продолжаем без бонуса.",
        "en": "Referral link not recognized. Continuing without bonus.",
    },
    "owner.referrals.title": {
        "ru": "Реферальная программа",
        "en": "Referral program",
    },
    "owner.referrals.current_value": {
        "ru": "Текущее вознаграждение: {value} кредитов.",
        "en": "Current reward: {value} credits.",
    },
    "owner.referrals.prompt": {
        "ru": "Отправьте целое число от 0 до {max}, чтобы изменить вознаграждение.",
        "en": "Send an integer between 0 and {max} to change the reward.",
    },
    "owner.referrals.saved": {
        "ru": "Сохранено: {value} кредитов.",
        "en": "Saved: {value} credits.",
    },
    "owner.referrals.reset": {
        "ru": "Сброшено к значению по умолчанию ({value}).",
        "en": "Reset to default ({value}).",
    },
    "owner.referrals.too_large": {
        "ru": "Значение должно быть в диапазоне 0–{max}.",
        "en": "Value must be in range 0-{max}.",
    },
    "owner.referrals.not_a_number": {
        "ru": "Пришлите целое число.",
        "en": "Send an integer.",
    },
    "owner.referrals.cancel_hint": {
        "ru": "Отправьте /cancel, чтобы отменить.",
        "en": "Send /cancel to abort.",
    },
    "owner.referrals.menu_button": {
        "ru": "Реферальная программа",
        "en": "Referrals",
    },
```

NB: placeholder convention — `{language}` is reserved by Translator (per SP3 memory). All vars used above (`credits`, `friends`, `value`, `max`) are safe.

- [ ] **Step 4: Mirror in 8 locale modules**

For each of `de.py`, `es.py`, `fr.py`, `hi.py`, `it.py`, `pt.py`, `tr.py`, `zh.py` under `src/quantuum/i18n/translations/`, append the same 16 keys to the module's `STRINGS` dict. Use the English text from Step 3 as the placeholder translation for each non-English locale — translators will refine later, but the keys must exist with non-empty strings.

Example for `de.py` (append before the closing `}` of STRINGS):

```python
    "btn.invite": "Freund einladen",
    "invite.title": "Lade Freunde zu diesem Bot ein.",
    "invite.link_label": "Dein Link",
    "invite.earned": "Verdient: {credits} Credits von {friends} Freunden.",
    "invite.share_text": "Probier diesen Bot",
    "invite.disabled": "Empfehlungen sind in diesem Bot deaktiviert.",
    "invite.unknown_code": "Empfehlungslink nicht erkannt. Fortsetzung ohne Bonus.",
    "owner.referrals.title": "Empfehlungsprogramm",
    "owner.referrals.current_value": "Aktuelle Belohnung: {value} Credits.",
    "owner.referrals.prompt": "Sende eine ganze Zahl zwischen 0 und {max}.",
    "owner.referrals.saved": "Gespeichert: {value} Credits.",
    "owner.referrals.reset": "Auf Standard zurückgesetzt ({value}).",
    "owner.referrals.too_large": "Wert muss zwischen 0 und {max} sein.",
    "owner.referrals.not_a_number": "Sende eine ganze Zahl.",
    "owner.referrals.cancel_hint": "Sende /cancel zum Abbrechen.",
    "owner.referrals.menu_button": "Empfehlungen",
```

For the other 7 locales, use any reasonable native translation OR copy the English value verbatim if you do not speak the language — the test only requires non-empty strings, and the existing SP3 commits show this pattern (English fallback strings populated in zh/hi/tr modules during the SP3 wave). **Do not invent Cyrillic, CJK, or Arabic strings if you are not confident — use the English text as the seed.**

- [ ] **Step 5: Re-run the i18n coverage test**

```bash
uv run pytest tests/test_referral_i18n.py -v
```

Expected: 144 parametrized cases pass (16 keys × (1 base test + 8 locales) + 4 placeholder assertions).

- [ ] **Step 6: Ruff sweep**

```bash
uv run ruff check src/quantuum/i18n/ tests/test_referral_i18n.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/ tests/test_referral_i18n.py
git commit -m "feat(sp4): i18n seed 16 referral keys"
```

---

## Task 4: Token dispatcher + `/start` payload parsing

**Files:**
- Create: `src/quantuum/bot/handlers/start_tokens.py`
- Create: `tests/test_start_token_dispatcher.py`
- Modify: `src/quantuum/bot/handlers/start.py`

- [ ] **Step 1: Write failing dispatcher tests**

Create `tests/test_start_token_dispatcher.py`:

```python
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.start_tokens import (
    dispatch_start_token,
    parse_start_payload,
    resolve_start_token,
)
from quantuum.common.datetime import utcnow
from quantuum.db.models import AuditLog, StartToken, StartTokenUse, Tenant
from quantuum.domain.referrals import REFERRAL_KIND, generate_referral_code


async def _tenant(session) -> Tenant:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    return t


async def _account(session, tenant_id: int, tg_id: int) -> int:
    acct = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_id=tg_id, username=f"u{tg_id}"
    )
    return acct.id


def test_parse_start_payload_extracts_code():
    assert parse_start_payload("/start ABC23K7Q") == "ABC23K7Q"
    assert parse_start_payload("/start  ABC23K7Q  ") == "ABC23K7Q"
    assert parse_start_payload("/start") is None
    assert parse_start_payload("/start ") is None
    assert parse_start_payload("") is None
    assert parse_start_payload(None) is None


def test_parse_start_payload_rejects_oversize():
    # Telegram caps start payload at 64 chars; reject longer values defensively.
    long = "X" * 65
    assert parse_start_payload(f"/start {long}") is None


async def test_resolve_start_token_returns_active(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    token = await resolve_start_token(session, code=code, tenant_id=t.id)
    assert token is not None
    assert token.code == code


async def test_resolve_start_token_unknown(session: AsyncSession):
    t = await _tenant(session)
    token = await resolve_start_token(session, code="NOPE0000", tenant_id=t.id)
    assert token is None


async def test_resolve_start_token_wrong_tenant(session: AsyncSession):
    t1 = await _tenant(session)
    t2 = Tenant(slug="t2", display_name="T2")
    session.add(t2)
    await session.flush()
    aid = await _account(session, t1.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t1.id)
    assert await resolve_start_token(session, code=code, tenant_id=t2.id) is None


async def test_resolve_start_token_disabled(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    tok = await session.get(StartToken, code)
    tok.status = "disabled"
    await session.flush()
    assert await resolve_start_token(session, code=code, tenant_id=t.id) is None


async def test_resolve_start_token_expired(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    tok = await session.get(StartToken, code)
    tok.expires_at = utcnow() - timedelta(seconds=1)
    await session.flush()
    assert await resolve_start_token(session, code=code, tenant_id=t.id) is None


async def test_resolve_start_token_maxed(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    tok = await session.get(StartToken, code)
    tok.max_uses = 1
    tok.used_count = 1
    await session.flush()
    assert await resolve_start_token(session, code=code, tenant_id=t.id) is None


async def test_dispatch_referral_records_use(session: AsyncSession):
    t = await _tenant(session)
    referrer = await _account(session, t.id, 1001)
    referee = await _account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    token = await resolve_start_token(session, code=code, tenant_id=t.id)

    await dispatch_start_token(session, token=token, account_id=referee)

    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().one()
    assert use.token_code == code
    assert use.claimed_at is None

    tok = await session.get(StartToken, code)
    assert tok.used_count == 1

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "referral.attributed"))
    ).scalars().all()
    assert len(audit) == 1


async def test_dispatch_referral_self_referral_silent(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    token = await resolve_start_token(session, code=code, tenant_id=t.id)

    await dispatch_start_token(session, token=token, account_id=aid)

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == aid)
        )
    ).scalars().all()
    assert uses == []


async def test_dispatch_referral_already_attributed_silent(session: AsyncSession):
    t = await _tenant(session)
    r1 = await _account(session, t.id, 1001)
    r2 = await _account(session, t.id, 1002)
    referee = await _account(session, t.id, 2001)
    code1 = await generate_referral_code(session, account_id=r1, tenant_id=t.id)
    code2 = await generate_referral_code(session, account_id=r2, tenant_id=t.id)
    tok1 = await resolve_start_token(session, code=code1, tenant_id=t.id)
    tok2 = await resolve_start_token(session, code=code2, tenant_id=t.id)

    await dispatch_start_token(session, token=tok1, account_id=referee)
    await dispatch_start_token(session, token=tok2, account_id=referee)

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().all()
    assert len(uses) == 1
    assert uses[0].token_code == code1
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_start_token_dispatcher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `src/quantuum/bot/handlers/start_tokens.py`**

```python
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import StartToken, StartTokenUse
from quantuum.domain.audit import record_audit
from quantuum.domain.referrals import REFERRAL_KIND
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

_MAX_PAYLOAD_LEN = 64


def parse_start_payload(text: str | None) -> str | None:
    """Extract the deep-link payload from a `/start ...` message text.

    Returns None if no payload, empty payload, or payload exceeds Telegram's
    64-char cap (defensive guard).
    """
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if not payload or len(payload) > _MAX_PAYLOAD_LEN:
        return None
    return payload


async def resolve_start_token(
    session: AsyncSession, *, code: str, tenant_id: int
) -> StartToken | None:
    """Look up a start_token by code, scoped to tenant_id. Returns None if
    missing, wrong tenant, disabled, expired, or maxed-out.
    """
    token = await session.get(StartToken, code)
    if token is None or token.tenant_id != tenant_id:
        return None
    if token.status != "active":
        return None
    if token.expires_at is not None and token.expires_at <= utcnow():
        return None
    if token.max_uses is not None and token.used_count >= token.max_uses:
        return None
    return token


async def dispatch_start_token(
    session: AsyncSession, *, token: StartToken, account_id: int
) -> None:
    """Route a resolved token to its kind-specific handler. Unknown kinds
    log a warning and no-op so older bot builds never crash on future codes.
    """
    handler = _HANDLERS.get(token.kind)
    if handler is None:
        logger.warning("start_token.unknown_kind", kind=token.kind, code=token.code)
        return
    await handler(session, token=token, account_id=account_id)


async def handle_referral_token(
    session: AsyncSession, *, token: StartToken, account_id: int
) -> None:
    """Record a referral attribution. Silent no-op on self-referral and on
    accounts already attributed (UNIQUE constraint).
    """
    if token.owner_account_id == account_id:
        return
    use = StartTokenUse(
        token_code=token.code,
        account_id=account_id,
        used_at=utcnow(),
    )
    session.add(use)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return
    token.used_count += 1
    session.add(token)
    await session.flush()
    await record_audit(
        session,
        tenant_id=token.tenant_id,
        actor_account_id=account_id,
        action="referral.attributed",
        entity_type="start_token_use",
        entity_id=use.id,
        payload={
            "referee_id": account_id,
            "referrer_id": token.owner_account_id,
            "code": token.code,
        },
    )


_HANDLERS = {
    REFERRAL_KIND: handle_referral_token,
}
```

- [ ] **Step 4: Run dispatcher tests, confirm green**

```bash
uv run pytest tests/test_start_token_dispatcher.py -v
```

Expected: all PASS.

- [ ] **Step 5: Wire payload parsing into `/start`**

Modify `src/quantuum/bot/handlers/start.py`:

```python
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.bot.handlers.start_tokens import (
    dispatch_start_token,
    parse_start_payload,
    resolve_start_token,
)
from quantuum.bot.ui.keyboards import language_picker_kb
from quantuum.db.bootstrap import get_sessionmaker
from quantuum.db.models import Account
from quantuum.i18n import Translator

router = Router()


@router.message(CommandStart())
async def on_start(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    payload = parse_start_payload(message.text)
    if payload:
        async with get_sessionmaker()() as session:
            token = await resolve_start_token(session, code=payload, tenant_id=tenant_id)
            if token is None:
                await message.answer(await i18n("invite.unknown_code"))
            else:
                await dispatch_start_token(session, token=token, account_id=account.id)
            await session.commit()

    if account.preferred_lang is None:
        await message.answer(
            await i18n("lang.prompt"),
            reply_markup=await language_picker_kb(tenant_id, action="setup"),
        )
        return
    await message.answer(await i18n("start.welcome"))
    await show_main_menu(message, tenant_id, i18n)
```

NB: verify the actual `get_sessionmaker` import path matches the existing project convention. If it lives elsewhere (e.g., `quantuum.db.session`), adjust the import.

- [ ] **Step 6: Ruff sweep**

```bash
uv run ruff check src/quantuum/bot/handlers/start.py src/quantuum/bot/handlers/start_tokens.py tests/test_start_token_dispatcher.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/handlers/start.py src/quantuum/bot/handlers/start_tokens.py tests/test_start_token_dispatcher.py
git commit -m "feat(sp4): start_token dispatcher + /start payload parsing"
```

---

## Task 5: `consume_quota` integration — fire payout on first paid spend

**Files:**
- Modify: `src/quantuum/domain/quota.py`
- Create: `tests/test_consume_quota_referral_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_consume_quota_referral_integration.py`:

```python
import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    Payment,
    StartTokenUse,
    Tenant,
)
from quantuum.domain.quota import consume_quota
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    generate_referral_code,
)


async def _setup(session: AsyncSession):
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    referrer = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=1001, username="ref"
        )
    ).id
    referee = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=2001, username="new"
        )
    ).id
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    session.add(AccountBalance(account_id=referrer, package_credits=0))
    session.add(AccountBalance(account_id=referee, package_credits=10))
    await session.flush()
    return t, referrer, referee


async def test_consume_quota_fires_payout_when_paid(session: AsyncSession):
    t, referrer, referee = await _setup(session)
    session.add(
        Payment(
            tenant_id=t.id, account_id=referee, amount_cents=100,
            status="paid", paid_at=utcnow(),
        )
    )
    await session.flush()

    charged = await consume_quota(session, referee, kind="qa")
    assert charged == "package"

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS

    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().one()
    assert use.claimed_at is not None


async def test_consume_quota_no_payout_without_payment(session: AsyncSession):
    t, referrer, referee = await _setup(session)
    charged = await consume_quota(session, referee, kind="qa")
    assert charged == "package"

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == 0
    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().one()
    assert use.claimed_at is None


async def test_consume_quota_no_double_payout(session: AsyncSession):
    t, referrer, referee = await _setup(session)
    session.add(
        Payment(
            tenant_id=t.id, account_id=referee, amount_cents=100,
            status="paid", paid_at=utcnow(),
        )
    )
    # bump referee balance so second spend can succeed
    bal_referee = await session.get(AccountBalance, referee)
    bal_referee.package_credits = 10
    await session.flush()

    await consume_quota(session, referee, kind="qa")
    await consume_quota(session, referee, kind="qa")

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS  # exactly one bump


async def test_consume_quota_payout_failure_does_not_block_spend(
    session: AsyncSession, monkeypatch
):
    """If maybe_payout_referral raises, the spend still commits."""
    t, referrer, referee = await _setup(session)
    session.add(
        Payment(
            tenant_id=t.id, account_id=referee, amount_cents=100,
            status="paid", paid_at=utcnow(),
        )
    )
    await session.flush()

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated payout failure")

    import quantuum.domain.quota as quota_mod
    monkeypatch.setattr(quota_mod, "maybe_payout_referral", _boom)

    charged = await consume_quota(session, referee, kind="qa")
    assert charged == "package"

    bal_referee = await session.get(AccountBalance, referee)
    assert bal_referee.package_credits == 9  # spend went through
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_consume_quota_referral_integration.py -v
```

Expected: ImportError (no `maybe_payout_referral` in quota module yet) or assertion fail.

- [ ] **Step 3: Patch `consume_quota`**

Modify `src/quantuum/domain/quota.py`:

At the top, add the import:

```python
from quantuum.domain.referrals import maybe_payout_referral
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)
```

(If `logger` already exists in the module, do not redeclare.)

In `consume_quota`, immediately after `await session.commit()` on the `"package"` branch (the one that currently returns `"package"` at line ~72), insert the payout call inside a try/except wrapper:

```python
    if balance.package_credits >= cost_units:
        # ... existing FIFO drain + balance decrement ...
        balance.package_credits -= cost_units
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        try:
            await maybe_payout_referral(session, referee_account_id=account_id)
            await session.commit()
        except Exception:
            logger.exception("referral_payout_failed", account_id=account_id)
            await session.rollback()
        return "package"
```

- [ ] **Step 4: Run integration tests, confirm green**

```bash
uv run pytest tests/test_consume_quota_referral_integration.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run existing quota tests to confirm no regression**

```bash
uv run pytest tests/test_quota*.py tests/test_consume_quota*.py -v
```

Expected: existing quota tests still pass.

- [ ] **Step 6: Ruff sweep**

```bash
uv run ruff check src/quantuum/domain/quota.py tests/test_consume_quota_referral_integration.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/domain/quota.py tests/test_consume_quota_referral_integration.py
git commit -m "feat(sp4): consume_quota fires referral payout on package spend"
```

---

## Task 6: `/invite` handler + main menu button + tenant feature flag

**Files:**
- Modify: `src/quantuum/domain/tenant_features.py` (append `"referrals"`)
- Modify: `src/quantuum/bot/ui/keyboards.py` (gated Invite button)
- Modify: `src/quantuum/bot/handlers/menu.py` (route Invite label)
- Modify: `src/quantuum/bot/ui/text.py` (register `btn.invite` label source)
- Create: `src/quantuum/bot/handlers/invite.py`
- Create: `tests/test_invite_handler.py`

- [ ] **Step 1: Write failing invite tests**

Create `tests/test_invite_handler.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.invite import show_invite
from quantuum.db.models import StartToken, Tenant, TenantBot
from quantuum.domain.referrals import REFERRAL_KIND
from quantuum.domain.tenant_features import FEATURE_KEYS, set_feature_enabled
from quantuum.i18n import Translator


def test_referrals_feature_key_registered():
    assert "referrals" in FEATURE_KEYS


async def _tenant_bot(session: AsyncSession) -> tuple[Tenant, TenantBot]:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    bot = TenantBot(tenant_id=t.id, bot_username="my_bot")
    session.add(bot)
    await session.flush()
    return t, bot


async def test_show_invite_lazy_creates_referral_code(session: AsyncSession):
    t, _ = await _tenant_bot(session)
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=1001, username="u1"
        )
    ).id

    message = MagicMock()
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=t.id, lang="en")

    await show_invite(message, account_id=aid, tenant_id=t.id, i18n=i18n)

    token = (
        (
            await session.execute(
                select(StartToken).where(
                    StartToken.kind == REFERRAL_KIND,
                    StartToken.owner_account_id == aid,
                )
            )
        )
        .scalars()
        .first()
    )
    assert token is not None


async def test_show_invite_message_contains_link_and_stats(session: AsyncSession):
    t, _ = await _tenant_bot(session)
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=1001, username="u1"
        )
    ).id

    message = MagicMock()
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=t.id, lang="en")

    await show_invite(message, account_id=aid, tenant_id=t.id, i18n=i18n)

    args, kwargs = message.answer.call_args
    body = args[0] if args else kwargs.get("text", "")
    assert "my_bot" in body
    assert "?start=" in body
    # newly created code -> claimed 0
    assert "0" in body
    # reply_markup carries a share-url button
    markup = kwargs.get("reply_markup")
    assert markup is not None


async def test_show_invite_disabled_when_feature_off(session: AsyncSession):
    t, _ = await _tenant_bot(session)
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=1001, username="u1"
        )
    ).id
    await set_feature_enabled(
        session, tenant_id=t.id, key="referrals", enabled=False, by_account_id=aid
    )

    message = MagicMock()
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=t.id, lang="en")

    await show_invite(message, account_id=aid, tenant_id=t.id, i18n=i18n)

    args, kwargs = message.answer.call_args
    body = args[0] if args else kwargs.get("text", "")
    # disabled message rendered, no link generated
    token = (
        (
            await session.execute(
                select(StartToken).where(StartToken.owner_account_id == aid)
            )
        )
        .scalars()
        .first()
    )
    assert token is None
    assert kwargs.get("reply_markup") is None
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_invite_handler.py -v
```

Expected: ImportError + AssertionError on `"referrals" in FEATURE_KEYS`.

- [ ] **Step 3: Register `referrals` in `FEATURE_KEYS`**

Modify `src/quantuum/domain/tenant_features.py:7-20`:

```python
FEATURE_KEYS: tuple[str, ...] = (
    "qa",
    "blueprint",
    "transits",
    "daily",
    "reading.bazi",
    "reading.numerology",
    "reading.human_design",
    "reading.astrology",
    "reading.vedic",
    "reading.gene_keys",
    "reading.mayan",
    "reading.aspects",
    "referrals",
)
```

- [ ] **Step 4: Implement `src/quantuum/bot/handlers/invite.py`**

```python
from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from quantuum.bot.ui import text
from quantuum.db.bootstrap import get_sessionmaker
from quantuum.db.models import Account, TenantBot
from quantuum.domain.referrals import (
    generate_referral_code,
    get_referral_stats,
)
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator

router = Router()

_INVITE_LABELS = text.menu_button_labels("btn.invite")


async def _tenant_bot_username(session, tenant_id: int) -> str | None:
    row = (
        await session.execute(
            select(TenantBot).where(TenantBot.tenant_id == tenant_id)
        )
    ).scalars().first()
    return row.bot_username if row else None


async def show_invite(
    message: Message, *, account_id: int, tenant_id: int, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, tenant_id, "referrals"):
            await message.answer(await i18n("invite.disabled"))
            return

        code = await generate_referral_code(
            session, account_id=account_id, tenant_id=tenant_id
        )
        stats = await get_referral_stats(session, account_id=account_id)
        username = await _tenant_bot_username(session, tenant_id)
        await session.commit()

    if not username:
        await message.answer(await i18n("invite.disabled"))
        return

    link = f"https://t.me/{username}?start={code}"
    earned_line = await i18n(
        "invite.earned",
        credits=stats["claimed"] * 10,  # display assumes default reward; refined below
        friends=stats["claimed"],
    )
    body = (
        f"{await i18n('invite.title')}\n\n"
        f"{await i18n('invite.link_label')}: {link}\n"
        f"{earned_line}"
    )

    share_text = await i18n("invite.share_text")
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await i18n("btn.invite"), url=share_url)]
        ]
    )
    await message.answer(body, reply_markup=kb)


@router.message(Command("invite"))
async def on_invite_cmd(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_invite(message, account_id=account.id, tenant_id=tenant_id, i18n=i18n)


@router.message(F.text.in_(_INVITE_LABELS))
async def on_invite_btn(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_invite(message, account_id=account.id, tenant_id=tenant_id, i18n=i18n)
```

NB: the "10" placeholder on `earned_line.credits` is a display approximation — we report `claimed * current_reward_credits`. Fetch via `get_reward_credits` instead:

Replace the body assembly with:

```python
    from quantuum.domain.referrals import get_reward_credits  # local import to avoid cycle
    async with get_sessionmaker()() as session:
        reward = await get_reward_credits(session, tenant_id=tenant_id)
    earned_line = await i18n(
        "invite.earned",
        credits=stats["claimed"] * reward,
        friends=stats["claimed"],
    )
```

Or — cleaner — fetch `reward` inside the first session block before commit. Use that pattern; keep the implementation clean.

- [ ] **Step 5: Add Invite button to `main_menu_kb`**

Modify `src/quantuum/bot/ui/keyboards.py:46-87`. Inside `main_menu_kb`, after the `_add(await i18n("btn.language"))` line (or before — placement TBD by visual taste; put it right after `btn.help`), gate on the new flag:

```python
    if flags.get("referrals", True):
        _add(await i18n("btn.invite"))
```

Insert this so the button appears between Help and Language.

- [ ] **Step 6: Register the button-label source**

Check `src/quantuum/bot/ui/text.py` for the `all_menu_labels` / `menu_button_labels` definitions. They likely enumerate the known menu keys. Add `"btn.invite"` to that enumeration so the labels-across-languages helper picks it up.

If `text.py` doesn't have a central registry and instead each handler in `menu.py` declares its own `_*_LABELS`, then in `menu.py` add:

```python
_INVITE_LABELS = text.menu_button_labels("btn.invite")
```

But the actual `@router.message(F.text.in_(_INVITE_LABELS))` handler lives in `invite.py`. Wire it up by registering the invite router in the bot's main router setup (find where other handler routers are included and add `dp.include_router(invite.router)`).

- [ ] **Step 7: Wire invite.router into the bot dispatcher**

Find the file that does `dp.include_router(...)` for existing handlers (likely `src/quantuum/bot/main.py` or `bot/__init__.py`). Add:

```python
from quantuum.bot.handlers import invite as invite_handlers
...
dp.include_router(invite_handlers.router)
```

- [ ] **Step 8: Run invite tests, confirm green**

```bash
uv run pytest tests/test_invite_handler.py -v
```

Expected: all PASS.

- [ ] **Step 9: Ruff sweep**

```bash
uv run ruff check src/quantuum/bot/handlers/invite.py src/quantuum/bot/ui/keyboards.py src/quantuum/bot/handlers/menu.py src/quantuum/domain/tenant_features.py tests/test_invite_handler.py
```

Expected: no findings.

- [ ] **Step 10: Commit**

```bash
git add src/quantuum/bot/handlers/invite.py src/quantuum/bot/ui/keyboards.py src/quantuum/bot/handlers/menu.py src/quantuum/bot/ui/text.py src/quantuum/bot/main.py src/quantuum/domain/tenant_features.py tests/test_invite_handler.py
git commit -m "feat(sp4): /invite + menu button + referrals tenant flag"
```

(Adjust the file list per what you actually touched. If `bot/main.py` is the wrong path, substitute the correct dispatcher-setup file.)

---

## Task 7: Owner console Referrals submenu + FSM

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py` (add `OwnerReferralsCb`)
- Modify: `src/quantuum/bot/handlers/owner_console.py` (button, submenu, FSM)
- Create: `tests/test_owner_referrals.py`

Mirror SP3 Branding pattern at `src/quantuum/bot/handlers/owner_console.py` (the `OwnerBranding` block).

- [ ] **Step 1: Write failing owner tests**

Create `tests/test_owner_referrals.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import OwnerReferralsCb
from quantuum.db.models import AuditLog, Tenant
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    REFERRAL_REWARD_CONFIG_KEY,
    get_reward_credits,
)
from quantuum.i18n import Translator


def test_owner_referrals_cb_class_exists():
    cb = OwnerReferralsCb(action="open")
    assert cb.action == "open"


async def _setup(session: AsyncSession) -> tuple[int, int]:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=9001, username="owner", is_owner=True
        )
        if False
        else await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_id=9001, username="owner"
        )
    ).id
    return t.id, aid


async def test_referrals_open_renders_current_value(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_open

    tid, aid = await _setup(session)
    query = MagicMock()
    query.message = MagicMock()
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")
    cb = OwnerReferralsCb(action="open")

    await on_referrals_open(query, cb, account_id=aid, tenant_id=tid, i18n=i18n)

    args, kwargs = query.message.answer.call_args
    body = args[0] if args else kwargs.get("text", "")
    assert str(DEFAULT_REWARD_CREDITS) in body


async def test_referrals_edit_saves_value(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    message = MagicMock()
    message.text = "25"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")

    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    assert await get_reward_credits(session, tenant_id=tid) == 25


async def test_referrals_edit_validation_too_large(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    message = MagicMock()
    message.text = "9999"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")

    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS
    # state retained for retry
    assert (await state.get_state()) is not None


async def test_referrals_edit_validation_not_a_number(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    message = MagicMock()
    message.text = "abc"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")

    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS
    assert (await state.get_state()) is not None


async def test_referrals_reset_clears_override(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )

    # set non-default, then reset
    msg_set = MagicMock()
    msg_set.text = "50"
    msg_set.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")
    await on_referrals_value(
        msg_set, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )
    assert await get_reward_credits(session, tenant_id=tid) == 50

    msg_reset = MagicMock()
    msg_reset.text = "/reset"
    msg_reset.answer = AsyncMock()
    await on_referrals_value(
        msg_reset, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )
    assert await get_reward_credits(session, tenant_id=tid) == DEFAULT_REWARD_CREDITS


async def test_referrals_config_set_writes_audit(session: AsyncSession):
    from quantuum.bot.handlers.owner_console import on_referrals_value

    tid, aid = await _setup(session)
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=aid, user_id=aid),
    )
    message = MagicMock()
    message.text = "33"
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=tid, lang="en")
    await on_referrals_value(
        message, state=state, account_id=aid, tenant_id=tid, i18n=i18n
    )

    rows = (
        (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "referral.config_set")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) >= 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_owner_referrals.py -v
```

Expected: ImportError on `OwnerReferralsCb` and `on_referrals_open` / `on_referrals_value`.

- [ ] **Step 3: Add `OwnerReferralsCb` to `src/quantuum/bot/ui/callbacks.py`**

Append at end of file:

```python
class OwnerReferralsCb(CallbackData, prefix="oref"):
    action: str       # open | edit | reset
    tenant_id: int = 0
```

- [ ] **Step 4: Implement owner referrals submenu in `src/quantuum/bot/handlers/owner_console.py`**

Add imports near top:

```python
from quantuum.bot.ui.callbacks import OwnerReferralsCb
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    MAX_REWARD_CREDITS,
    get_reward_credits,
    reset_reward_credits,
    set_reward_credits,
)
```

Add FSM state class (mirrors `OwnerBranding`):

```python
class OwnerReferrals(StatesGroup):
    awaiting_value = State()
```

Add a Referrals button to the `/manage` keyboard (next to the Branding button SP3 added). In the keyboard-building function for `on_manage`:

```python
    b.button(
        text=await i18n("owner.referrals.menu_button"),
        callback_data=OwnerReferralsCb(action="open").pack(),
    )
```

Add handlers:

```python
async def _referrals_keyboard(i18n: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=await i18n("owner.referrals.menu_button"),
        callback_data=OwnerReferralsCb(action="edit").pack(),
    )
    b.adjust(1)
    return b.as_markup()


@router.callback_query(OwnerReferralsCb.filter(F.action == "open"))
async def on_referrals_open(
    query: CallbackQuery,
    callback_data: OwnerReferralsCb,
    account_id: int,
    tenant_id: int,
    i18n: Translator,
) -> None:
    async with get_sessionmaker()() as session:
        current = await get_reward_credits(session, tenant_id=tenant_id)
    body = (
        f"{await i18n('owner.referrals.title')}\n\n"
        f"{await i18n('owner.referrals.current_value', value=current)}"
    )
    await query.message.answer(body, reply_markup=await _referrals_keyboard(i18n))
    await query.answer()


@router.callback_query(OwnerReferralsCb.filter(F.action == "edit"))
async def on_referrals_edit(
    query: CallbackQuery,
    callback_data: OwnerReferralsCb,
    state: FSMContext,
    tenant_id: int,
    i18n: Translator,
) -> None:
    await state.set_state(OwnerReferrals.awaiting_value)
    await query.message.answer(
        await i18n("owner.referrals.prompt", max=MAX_REWARD_CREDITS)
        + "\n"
        + await i18n("owner.referrals.cancel_hint"),
    )
    await query.answer()


@router.message(OwnerReferrals.awaiting_value, Command("cancel"))
async def on_referrals_cancel(
    message: Message, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await message.answer(await i18n("menu.cancelled"))


@router.message(OwnerReferrals.awaiting_value)
async def on_referrals_value(
    message: Message,
    state: FSMContext,
    account_id: int,
    tenant_id: int,
    i18n: Translator,
) -> None:
    text_in = (message.text or "").strip()

    if text_in == "/reset":
        async with get_sessionmaker()() as session:
            await reset_reward_credits(
                session, tenant_id=tenant_id, by_account_id=account_id
            )
            await session.commit()
        await state.clear()
        await message.answer(
            await i18n("owner.referrals.reset", value=DEFAULT_REWARD_CREDITS)
        )
        return

    try:
        value = int(text_in)
    except (TypeError, ValueError):
        await message.answer(await i18n("owner.referrals.not_a_number"))
        return  # stay in state

    if value < 0 or value > MAX_REWARD_CREDITS:
        await message.answer(
            await i18n("owner.referrals.too_large", max=MAX_REWARD_CREDITS)
        )
        return  # stay in state

    async with get_sessionmaker()() as session:
        try:
            await set_reward_credits(
                session,
                tenant_id=tenant_id,
                value=value,
                by_account_id=account_id,
            )
            await session.commit()
        except ValueError:
            await message.answer(
                await i18n("owner.referrals.too_large", max=MAX_REWARD_CREDITS)
            )
            return  # stay in state

    await state.clear()
    await message.answer(await i18n("owner.referrals.saved", value=value))
```

The test in Step 1 dispatches `on_referrals_value` *directly* (no router round-trip). Make sure the function signature accepts injected `account_id`, `tenant_id`, `i18n` so tests can call it. The router handler must extract these from the standard aiogram middleware context — the same pattern SP3 used in `on_branding_value`.

- [ ] **Step 5: Run owner tests, confirm green**

```bash
uv run pytest tests/test_owner_referrals.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 6: Ruff sweep**

```bash
uv run ruff check src/quantuum/bot/handlers/owner_console.py src/quantuum/bot/ui/callbacks.py tests/test_owner_referrals.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/handlers/owner_console.py src/quantuum/bot/ui/callbacks.py tests/test_owner_referrals.py
git commit -m "feat(sp4): owner console Referrals submenu + FSM"
```

---

## Task 8: Full suite gate + ruff sweep

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass. If any regression appears, fix at root cause and re-run. Do NOT mark this task complete until the suite is green.

- [ ] **Step 2: Ruff sweep all touched source + tests**

```bash
uv run ruff check src/ tests/
```

Expected: no findings on SP4-touched files. Pre-existing findings outside SP4 may exist — do not address them in this task.

- [ ] **Step 3: Confirm no commits left unstaged**

```bash
git status
```

Expected: clean working tree. All SP4 work captured in the 7 prior commits.

- [ ] **Step 4: Final summary**

Report back: number of tests passing, ruff status, SP4 commit chain (`git log --oneline -10`). No code commit on this task — it is a gate.

---

## Plan Self-Review Notes

- **Spec coverage:** every spec section maps to a task — tables → T1; domain helpers → T2; i18n keys → T3; dispatcher + /start parsing → T4; consume_quota integration → T5; customer UX + tenant flag → T6; owner UX → T7; verification → T8.
- **Type consistency:** `REFERRAL_KIND`, `DEFAULT_REWARD_CREDITS`, `MAX_REWARD_CREDITS`, `REFERRAL_CODE_LENGTH`, `REFERRAL_REWARD_CONFIG_KEY` defined in T2 and re-imported by T4, T5, T6, T7 with the same names. `OwnerReferralsCb` defined in T7 step 3, used in handlers in step 4. `StartToken` / `StartTokenUse` defined in T1, used everywhere downstream.
- **Cross-task imports:** every later task only imports symbols introduced earlier in the plan.
- **Open implementation note for T6:** the precise file that wires routers (`bot/main.py` vs `bot/__init__.py`) was not verified during plan-writing. Implementer must locate the existing `dp.include_router(...)` site and add `invite.router` there. If the dispatcher uses a list-of-routers fixture instead, append to that list.

## Pre-Execution Setup Note

Before starting Task 1, confirm test DB is up:

```bash
docker ps --format '{{.Names}}' | grep -E 'postgres-test|quantuum-bot-postgres-test'
```

If absent, run:

```bash
docker compose -f docker-compose.test.yml up -d
```

Per `docker-loopback-quirk` memory: tests connect to the container's bridge IP (172.30.0.2), not localhost.
