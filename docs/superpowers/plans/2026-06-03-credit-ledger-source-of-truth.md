# Credit Ledger Source-of-Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `AccountPackage` ledger the single source of truth for credits so gifts, referral payouts, and welcome credits stop vanishing when a later payment triggers `recompute_account_balance`.

**Architecture:** Today `recompute_account_balance` (`domain/billing.py:85`) sets `package_credits = SUM(ledger rows)`, but gifts (`start_tokens.py:155`, `gifts.py:257`), referral payouts (`referrals.py:208`), and welcome credits (`auth/identity.py:18`) write only the `package_credits` counter and create no ledger row — so the next recompute erases them. The fix routes every credit grant through a new `grant_credits` helper that always inserts a ledger row, backfills existing counter-only balances with a one-time migration, and removes the dead free-trial branch. `consume_quota` and `refund_quota` already keep counter and ledger in lockstep, so their math is unchanged (only a dead branch removal and a row lock).

**Tech Stack:** Python, SQLModel/SQLAlchemy async, Alembic, PostgreSQL, pytest (asyncio auto mode; fixtures `session` and `default_tenant` from `tests/conftest.py`).

**Scope note:** This plan covers Workstream A *domain* changes only. The handler-level enqueue-atomicity (wrap charge→create→enqueue with `refund_quota` on queue failure across `qa`/`readings`/`transits`/`generate`) is a separate focused plan (`A-handlers`) to keep each plan reviewable. The divination ordering bug (a concrete data-loss case fixed by reordering, not by atomicity machinery) is included here as Task 9.

---

### Task 1: Add `source` column and make `plan_id` nullable on `AccountPackage`

**Files:**
- Modify: `src/quantuum/db/models.py` (class `AccountPackage`, around line 401)

- [ ] **Step 1: Edit the model**

In `src/quantuum/db/models.py`, change the `AccountPackage` class fields:

```python
class AccountPackage(SQLModel, table=True):
    __tablename__ = "account_packages"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="package_plans.id")
    source: str = Field(default="purchase")  # purchase | gift | referral | welcome | manual | backfill
    requests_remaining: int
    purchased_at: datetime = _dt_field(default_factory=utcnow)
    expires_at: datetime | None = _dt_field(default=None)
    payment_id: int | None = Field(default=None, foreign_key="payments.id")
    created_at: datetime = _dt_field(default_factory=utcnow)
```

- [ ] **Step 2: Verify the model imports cleanly**

Run: `python -c "from quantuum.db.models import AccountPackage; print(AccountPackage.__table__.c.keys())"`
Expected: the printed column list includes `source` and `plan_id`.

- [ ] **Step 3: Commit**

```bash
git add src/quantuum/db/models.py
git commit -m "feat(models): add AccountPackage.source, make plan_id nullable"
```

---

### Task 2: Alembic migration — nullable `plan_id`, `source` column, backfill counter-only balances

**Files:**
- Create: `alembic/versions/<generated>_account_packages_source_backfill.py`

- [ ] **Step 1: Generate an empty revision (auto-fills down_revision from current head)**

Run: `alembic revision -m "account_packages source backfill"`
Expected: prints the path to a new file under `alembic/versions/`. Open that file.

- [ ] **Step 2: Write the upgrade/downgrade**

Replace the generated `upgrade()`/`downgrade()` bodies with:

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    # 1. source column (default 'purchase' for existing purchase rows)
    op.add_column(
        "account_packages",
        sa.Column("source", sa.String(), nullable=False, server_default="purchase"),
    )
    # 2. plan_id becomes nullable (gifts/referrals/welcome have no plan)
    op.alter_column("account_packages", "plan_id", existing_type=sa.Integer(), nullable=True)

    # 3. Backfill: for any balance whose counter exceeds its valid ledger sum,
    #    insert one compensating ledger row for the difference so the first
    #    recompute after deploy does not wipe gift/referral/welcome credits.
    op.execute(
        """
        INSERT INTO account_packages
            (tenant_id, account_id, plan_id, source, requests_remaining,
             purchased_at, expires_at, payment_id, created_at)
        SELECT a.tenant_id,
               b.account_id,
               NULL,
               'backfill',
               b.package_credits - COALESCE(led.valid_sum, 0),
               now(), NULL, NULL, now()
        FROM account_balance b
        JOIN accounts a ON a.id = b.account_id
        LEFT JOIN (
            SELECT account_id, SUM(requests_remaining) AS valid_sum
            FROM account_packages
            WHERE requests_remaining > 0
              AND (expires_at IS NULL OR expires_at > now())
            GROUP BY account_id
        ) led ON led.account_id = b.account_id
        WHERE b.package_credits > COALESCE(led.valid_sum, 0)
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM account_packages WHERE source = 'backfill'")
    op.alter_column("account_packages", "plan_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("account_packages", "source")
```

- [ ] **Step 3: Apply the migration to the app DB**

Run: `alembic upgrade head`
Expected: completes without error; ends at the new revision.

- [ ] **Step 4: Verify upgrade/downgrade round-trips**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: both complete without error.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(db): migration for AccountPackage source + counter-only backfill"
```

---

### Task 3: Add `grant_credits` helper (single entry point for credit additions)

**Files:**
- Modify: `src/quantuum/domain/billing.py`
- Test: `tests/test_grant_credits.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_grant_credits.py`:

```python
from quantuum.db.models import AccountBalance, AccountPackage
from quantuum.domain.billing import (
    apply_package_payment,
    grant_credits,
    recompute_account_balance,
)


async def _account(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    return await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="gc1"
    )


async def test_grant_credits_creates_ledger_row_and_syncs_counter(session, default_tenant):
    acc = await _account(session, default_tenant)
    before = (await session.get(AccountBalance, acc.id)).package_credits

    pkg = await grant_credits(
        session, account_id=acc.id, tenant_id=default_tenant.id, amount=7, source="gift"
    )
    await session.commit()

    assert pkg.source == "gift"
    assert pkg.plan_id is None
    assert pkg.requests_remaining == 7
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == before + 7


async def test_granted_credits_survive_a_later_payment_recompute(session, default_tenant):
    """Regression for the source-of-truth bug: a gift must not vanish on recompute."""
    from quantuum.db.models import PackagePlan

    acc = await _account(session, default_tenant)
    await grant_credits(
        session, account_id=acc.id, tenant_id=default_tenant.id, amount=5, source="gift"
    )
    await session.commit()
    granted_total = (await session.get(AccountBalance, acc.id)).package_credits

    plan = PackagePlan(slug="p10", name="P10", request_count=10, price_cents=100)
    session.add(plan)
    await session.flush()
    await apply_package_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id, plan=plan, payment_id=None
    )

    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == granted_total + 10  # gift NOT wiped


async def test_grant_credits_rejects_non_positive(session, default_tenant):
    import pytest

    acc = await _account(session, default_tenant)
    with pytest.raises(ValueError):
        await grant_credits(
            session, account_id=acc.id, tenant_id=default_tenant.id, amount=0, source="gift"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_grant_credits.py -v`
Expected: FAIL with `ImportError: cannot import name 'grant_credits'`.

- [ ] **Step 3: Implement `grant_credits` and a flush-only counter sync**

In `src/quantuum/domain/billing.py`, add after `_ensure_balance` (after line 70):

```python
async def _sum_valid_packages(session, account_id: int) -> int:
    now = utcnow()
    result = await session.execute(
        select(AccountPackage.requests_remaining).where(
            AccountPackage.account_id == account_id,
            or_(AccountPackage.expires_at.is_(None), AccountPackage.expires_at > now),
        )
    )
    return int(sum(result.scalars().all()))


async def grant_credits(
    session,
    *,
    account_id: int,
    tenant_id: int,
    amount: int,
    source: str,
    expires_at=None,
    payment_id: int | None = None,
    plan_id: int | None = None,
) -> AccountPackage:
    """Add a credit ledger row from any source and sync the cached counter.

    The AccountPackage ledger is the single source of truth for package_credits;
    every non-purchase grant (gift, referral, welcome, manual) must go through here
    so a later recompute_account_balance does not erase the credits. Flush-only:
    the caller commits.
    """
    if amount < 1:
        raise ValueError(f"amount must be >= 1, got {amount}")
    now = utcnow()
    pkg = AccountPackage(
        tenant_id=tenant_id,
        account_id=account_id,
        plan_id=plan_id,
        source=source,
        requests_remaining=amount,
        purchased_at=now,
        expires_at=expires_at,
        payment_id=payment_id,
    )
    session.add(pkg)
    await session.flush()
    balance = await _ensure_balance(session, account_id)
    balance.package_credits = await _sum_valid_packages(session, account_id)
    balance.updated_at = now
    session.add(balance)
    await session.flush()
    return pkg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_grant_credits.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/billing.py tests/test_grant_credits.py
git commit -m "feat(billing): grant_credits ledger-backed credit helper"
```

---

### Task 4: Route welcome credits through the ledger

**Files:**
- Modify: `src/quantuum/auth/identity.py` (`_ensure_balance`, `_create_account`)
- Test: `tests/test_quota.py` (existing `test_new_account_receives_signup_credits` must stay green; add a regression test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_quota.py`:

```python
async def test_signup_credits_are_ledger_backed(session, default_tenant):
    from quantuum.db.models import AccountPackage
    from sqlmodel import select

    acc = await _make_account(session, default_tenant.id)
    rows = (
        await session.execute(
            select(AccountPackage).where(AccountPackage.account_id == acc.id)
        )
    ).scalars().all()
    assert any(r.source == "welcome" and r.requests_remaining > 0 for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_quota.py::test_signup_credits_are_ledger_backed -v`
Expected: FAIL — no welcome ledger row exists yet (welcome credits are counter-only).

- [ ] **Step 3: Rewire identity to grant via the ledger**

In `src/quantuum/auth/identity.py`, replace `_ensure_balance` and update `_create_account`:

```python
async def _ensure_balance(session, account_id: int) -> None:
    existing = await session.get(AccountBalance, account_id)
    if existing is None:
        # free_trial_used kept True for backward compatibility; welcome credits
        # (not the legacy one-shot trial) are the live mechanism and are granted
        # as a ledger row by the caller so recompute never erases them.
        session.add(AccountBalance(account_id=account_id, free_trial_used=True))
        await session.flush()


async def _create_account(session, tenant_id: int) -> Account:
    from quantuum.domain.billing import grant_credits

    account = Account(tenant_id=tenant_id)
    session.add(account)
    await session.flush()
    await _ensure_balance(session, account.id)
    await grant_credits(
        session,
        account_id=account.id,
        tenant_id=tenant_id,
        amount=SIGNUP_CREDITS,
        source="welcome",
    )
    return account
```

- [ ] **Step 4: Run the quota tests to verify they pass**

Run: `pytest tests/test_quota.py -v`
Expected: PASS — including `test_new_account_receives_signup_credits` (counter still equals `SIGNUP_CREDITS`, synced from the ledger) and the new ledger-backed test.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/auth/identity.py tests/test_quota.py
git commit -m "fix(credits): welcome credits as a ledger row, not counter-only"
```

---

### Task 5: Route gift redemption through the ledger

**Files:**
- Modify: `src/quantuum/bot/handlers/start_tokens.py` (`handle_gift_token`, around line 152-155)
- Test: `tests/test_start_token_dispatcher.py` (add a regression test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_start_token_dispatcher.py`:

```python
async def test_claimed_gift_is_ledger_backed(session, default_tenant):
    """A redeemed gift must create a ledger row so it survives recompute."""
    from sqlmodel import select

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import AccountPackage, StartToken
    from quantuum.bot.handlers.start_tokens import handle_gift_token

    recipient = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="giftee"
    )
    token = StartToken(
        code="giftcode1", kind="gift", tenant_id=default_tenant.id,
        owner_account_id=None, payload={"amount": 4}, status="active",
    )
    session.add(token)
    await session.commit()

    result = await handle_gift_token(session, token=token, account_id=recipient.id)
    await session.commit()

    assert result is not None and result.amount == 4
    rows = (
        await session.execute(
            select(AccountPackage).where(AccountPackage.account_id == recipient.id)
        )
    ).scalars().all()
    assert any(r.source == "gift" and r.requests_remaining == 4 for r in rows)
```

> Note: if `handle_gift_token`'s signature differs, adapt the call to match the existing one in `src/quantuum/bot/handlers/start_tokens.py`. Confirm the gift `kind` constant (`GIFT_KIND`) value before hardcoding `"gift"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_start_token_dispatcher.py::test_claimed_gift_is_ledger_backed -v`
Expected: FAIL — no gift ledger row (claim is counter-only).

- [ ] **Step 3: Rewire the gift claim**

In `src/quantuum/bot/handlers/start_tokens.py`, in `handle_gift_token`, replace the counter poke (lines ~152-155):

```python
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        return None
    bal.package_credits += amount
```

with a ledger grant:

```python
    from quantuum.domain.billing import grant_credits

    await grant_credits(
        session,
        account_id=account_id,
        tenant_id=locked.tenant_id,
        amount=amount,
        source="gift",
    )
```

(Remove the now-unused `bal`/`AccountBalance` lookup here if it is not used elsewhere in the function.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_start_token_dispatcher.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/start_tokens.py tests/test_start_token_dispatcher.py
git commit -m "fix(credits): gift redemption creates a ledger row"
```

---

### Task 6: Route gift sweep-refund through the ledger and guard missing balance

**Files:**
- Modify: `src/quantuum/domain/gifts.py` (`sweep_expired_gifts`, lines ~244-269)
- Test: `tests/test_gift_domain.py` (add a regression test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_gift_domain.py`:

```python
async def test_sweep_refund_is_ledger_backed(session, default_tenant):
    from datetime import timedelta
    from sqlmodel import select

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import AccountPackage, StartToken
    from quantuum.domain.gifts import sweep_expired_gifts

    sender = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="giftsender"
    )
    token = StartToken(
        code="expgift1", kind="gift", tenant_id=default_tenant.id,
        owner_account_id=sender.id, payload={"amount": 3}, status="active",
        expires_at=utcnow() - timedelta(days=1),
    )
    session.add(token)
    await session.commit()

    refunded = await sweep_expired_gifts(session, sender_account_id=sender.id)
    await session.commit()

    assert refunded == 1
    rows = (
        await session.execute(
            select(AccountPackage).where(AccountPackage.account_id == sender.id)
        )
    ).scalars().all()
    assert any(r.source == "gift" and r.requests_remaining == 3 for r in rows)
```

> Confirm the `sweep_expired_gifts` keyword name (`sender_account_id`) against the source before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gift_domain.py::test_sweep_refund_is_ledger_backed -v`
Expected: FAIL — sweep refund is counter-only (and may `AttributeError` if balance is missing).

- [ ] **Step 3: Rewire the sweep refund**

In `src/quantuum/domain/gifts.py`, in `sweep_expired_gifts`, remove the single `bal` lookup (line ~244) and replace the per-token counter poke (line ~257) `bal.package_credits += amount` with a ledger grant inside the loop:

```python
    from quantuum.domain.billing import grant_credits
    # ... inside the `for tok in candidates:` loop, after the amount<=0 guard:
        await grant_credits(
            session,
            account_id=sender_account_id,
            tenant_id=tok.tenant_id,
            amount=amount,
            source="gift",
        )
        tok.status = "refunded"
```

Delete the now-unused `bal = await session.get(AccountBalance, sender_account_id)` line (this also removes the `bal is None` `AttributeError` risk). Keep the existing `record_audit` call and `refunded += 1`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gift_domain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/gifts.py tests/test_gift_domain.py
git commit -m "fix(credits): gift sweep refund as ledger row, drop None-balance crash"
```

---

### Task 7: Route referral payout through the ledger

**Files:**
- Modify: `src/quantuum/domain/referrals.py` (`maybe_payout_referral`, line ~206-208)
- Test: `tests/test_referral_domain.py` (add a regression test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_referral_domain.py`:

```python
async def test_referral_payout_is_ledger_backed(session, default_tenant):
    from sqlmodel import select

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import (
        AccountPackage, Payment, StartToken, StartTokenUse,
    )
    from quantuum.domain.referrals import maybe_payout_referral

    referrer = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="ref_owner"
    )
    referee = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="ref_ee"
    )
    token = StartToken(
        code="refcode1", kind="referral", tenant_id=default_tenant.id,
        owner_account_id=referrer.id, status="active",
    )
    session.add(token)
    session.add(StartTokenUse(token_code="refcode1", account_id=referee.id))
    session.add(Payment(
        tenant_id=default_tenant.id, account_id=referee.id, provider_id=None,
        amount_cents=100, currency="XTR", status="paid",
    ))
    await session.commit()

    paid = await maybe_payout_referral(session, referee_account_id=referee.id)
    await session.commit()

    assert paid is True
    rows = (
        await session.execute(
            select(AccountPackage).where(AccountPackage.account_id == referrer.id)
        )
    ).scalars().all()
    assert any(r.source == "referral" and r.requests_remaining > 0 for r in rows)
```

> Confirm `Payment` required fields and the `REFERRAL_KIND` value against the source before running; adjust the constructor kwargs to match.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_referral_domain.py::test_referral_payout_is_ledger_backed -v`
Expected: FAIL — payout uses `adjust_package_credits` (counter-only), no referral ledger row.

- [ ] **Step 3: Rewire the payout**

In `src/quantuum/domain/referrals.py`, replace (line ~206-208):

```python
    amount = await get_reward_credits(session, tenant_id=token.tenant_id)
    if amount > 0:
        await adjust_package_credits(session, token.owner_account_id, amount)
```

with:

```python
    from quantuum.domain.billing import grant_credits

    amount = await get_reward_credits(session, tenant_id=token.tenant_id)
    if amount > 0:
        await grant_credits(
            session,
            account_id=token.owner_account_id,
            tenant_id=token.tenant_id,
            amount=amount,
            source="referral",
        )
```

Remove the now-unused `from quantuum.domain.accounts import adjust_package_credits` import at the top of the file if nothing else in the module uses it.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_referral_domain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/referrals.py tests/test_referral_domain.py
git commit -m "fix(credits): referral payout creates a ledger row"
```

---

### Task 8: Make manual owner credit grant/deduct ledger-backed

**Files:**
- Modify: `src/quantuum/domain/accounts.py` (`adjust_package_credits`, lines 58-73)
- Test: `tests/test_owner_console_actions.py` or `tests/test_grant_credits.py` (add a test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_grant_credits.py`:

```python
async def test_manual_grant_is_ledger_backed_and_deduct_drains(session, default_tenant):
    from sqlmodel import select

    from quantuum.db.models import AccountBalance, AccountPackage
    from quantuum.domain.accounts import adjust_package_credits

    acc = await _account(session, default_tenant)
    start = (await session.get(AccountBalance, acc.id)).package_credits

    after_grant = await adjust_package_credits(session, acc.id, 5)
    await session.commit()
    assert after_grant == start + 5
    rows = (
        await session.execute(
            select(AccountPackage).where(
                AccountPackage.account_id == acc.id, AccountPackage.source == "manual"
            )
        )
    ).scalars().all()
    assert any(r.requests_remaining == 5 for r in rows)

    after_deduct = await adjust_package_credits(session, acc.id, -3)
    await session.commit()
    assert after_deduct == after_grant - 3
    # counter stays consistent with the ledger sum
    from quantuum.domain.billing import _sum_valid_packages
    assert after_deduct == await _sum_valid_packages(session, acc.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_grant_credits.py::test_manual_grant_is_ledger_backed_and_deduct_drains -v`
Expected: FAIL — `adjust_package_credits` pokes the counter only; no `manual` ledger row.

- [ ] **Step 3: Rewire `adjust_package_credits` to the ledger**

In `src/quantuum/domain/accounts.py`, replace `adjust_package_credits` (lines 58-73) with:

```python
async def adjust_package_credits(session, account_id: int, delta: int) -> int:
    """Add (positive) or deduct (negative) package credits via the ledger.

    Positive delta inserts a 'manual' ledger row. Negative delta drains valid
    ledger rows oldest-expiring first, clamped at zero. The package_credits
    counter is kept equal to the valid ledger sum. Flushes; caller commits.
    Returns the new package_credits balance.
    """
    from quantuum.domain.billing import _sum_valid_packages, grant_credits
    from quantuum.domain.quota import _oldest_valid_package

    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
        session.add(bal)
        await session.flush()

    if delta > 0:
        acc = await session.get(Account, account_id)
        await grant_credits(
            session,
            account_id=account_id,
            tenant_id=acc.tenant_id,
            amount=delta,
            source="manual",
        )
        await session.refresh(bal)
        return bal.package_credits

    remaining = -delta
    while remaining > 0:
        pkg = await _oldest_valid_package(session, account_id)
        if pkg is None:
            break
        take = min(remaining, pkg.requests_remaining)
        pkg.requests_remaining -= take
        session.add(pkg)
        remaining -= take
    bal.package_credits = await _sum_valid_packages(session, account_id)
    bal.updated_at = utcnow()
    session.add(bal)
    await session.flush()
    return bal.package_credits
```

> `_oldest_valid_package` is the existing FIFO helper in `domain/quota.py:12`. `Account` is already imported in `accounts.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_grant_credits.py tests/test_owner_console_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/accounts.py tests/test_grant_credits.py
git commit -m "fix(credits): manual owner grant/deduct operate on the ledger"
```

---

### Task 9: Remove the dead free-trial branch in `consume_quota`

**Files:**
- Modify: `src/quantuum/domain/quota.py` (lines 47-52)
- Test: `tests/test_quota.py` (existing tests must stay green)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_quota.py`:

```python
async def test_consume_never_returns_trial(session, default_tenant):
    """The legacy one-shot trial is gone; first spend is always a package spend."""
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "package"
```

- [ ] **Step 2: Run test to verify it passes already, then prove the branch is dead**

Run: `pytest tests/test_quota.py::test_consume_never_returns_trial -v`
Expected: PASS (accounts are created with `free_trial_used=True`, so the branch is already skipped). This test guards the behavior; the next step removes the now-dead code.

- [ ] **Step 3: Delete the dead branch**

In `src/quantuum/domain/quota.py`, remove lines 47-52:

```python
    if not balance.free_trial_used and kind == "blueprint":
        balance.free_trial_used = True
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "trial"
```

Leave the rest of `consume_quota` unchanged (subscription check, package drain, referral payout).

- [ ] **Step 4: Run the full quota suite to verify it passes**

Run: `pytest tests/test_quota.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/quota.py tests/test_quota.py
git commit -m "refactor(quota): remove dead free-trial branch"
```

---

### Task 10: Lock the `Request` row in `refund_quota` (double-refund guard)

**Files:**
- Modify: `src/quantuum/domain/quota.py` (`refund_quota`, line 88)
- Test: `tests/test_quota.py` (add a guard test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_quota.py`:

```python
async def test_refund_is_idempotent(session, default_tenant):
    """A second refund of the same request must not credit again."""
    from quantuum.db.models import AccountBalance, Request

    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against="package", cost_units=1,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)
    once = (await session.get(AccountBalance, acc.id)).package_credits
    await refund_quota(session, req.id)  # second call must be a no-op
    twice = (await session.get(AccountBalance, acc.id)).package_credits
    assert twice == once
```

- [ ] **Step 2: Run test to verify it passes or fails**

Run: `pytest tests/test_quota.py::test_refund_is_idempotent -v`
Expected: PASS sequentially (the existing `charged_against in (None, "none")` guard already covers serial calls). This test documents the invariant; Step 3 adds the row lock that makes it hold under concurrency.

- [ ] **Step 3: Add the row lock**

In `src/quantuum/domain/quota.py`, change the first line of `refund_quota` (line 88) from:

```python
    request = await session.get(Request, request_id)
```

to:

```python
    request = await session.get(Request, request_id, with_for_update=True)
```

- [ ] **Step 4: Run the quota suite to verify it passes**

Run: `pytest tests/test_quota.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/quota.py tests/test_quota.py
git commit -m "fix(quota): lock Request row in refund to prevent double-refund"
```

---

### Task 11: Divination — check natal profile before charging (lost-credit bug)

**Files:**
- Modify: `src/quantuum/bot/handlers/divination.py` (`_perform_draw_and_enqueue`, lines 159-174)
- Test: `tests/test_divination_handler.py` (add a regression test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_divination_handler.py` (adapt fixtures/mocks to the patterns already in that file):

```python
async def test_divination_no_profile_does_not_charge(session, default_tenant, monkeypatch):
    """If the account has no natal profile, no credit may be consumed."""
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import AccountBalance
    from quantuum.bot.handlers import divination

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="divuser"
    )
    before = (await session.get(AccountBalance, acc.id)).package_credits

    # Build the minimal state/message doubles the handler needs. See the existing
    # tests in this file for the established Message/FSMContext fakes and reuse them.
    # The key assertion: after invoking the draw with no NatalProfile, the balance
    # is unchanged.
    ...  # invoke _perform_draw_and_enqueue with kind set and no profile

    after = (await session.get(AccountBalance, acc.id)).package_credits
    assert after == before
```

> The doubles for `message_for_reply`, `state`, and `i18n` already exist in `tests/test_divination_handler.py` — reuse them rather than inventing new ones. The assertion that matters is `after == before`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_divination_handler.py::test_divination_no_profile_does_not_charge -v`
Expected: FAIL — `consume_quota` runs (and commits) before the profile check, so `after == before - 1`.

- [ ] **Step 3: Reorder — profile check before charge**

In `src/quantuum/bot/handlers/divination.py`, in `_perform_draw_and_enqueue`, move the profile check above the charge so the block reads:

```python
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message_for_reply.answer(await i18n("readings.no_profile"))
            await state.clear()
            return

        try:
            charged = await consume_quota(session, account.id, "reading", cost_units=1)
        except InsufficientFundsError:
            await message_for_reply.answer(
                await i18n("readings.no_quota"),
                reply_markup=await _buy_offer_kb(i18n),
            )
            await state.clear()
            return
```

(The draw/enqueue code below stays unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_divination_handler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/divination.py tests/test_divination_handler.py
git commit -m "fix(divination): check natal profile before consuming quota"
```

---

### Task 12: Full regression sweep

- [ ] **Step 1: Run the whole suite**

Run: `pytest -q`
Expected: all tests pass. Pay attention to `test_quota.py`, `test_grant_credits.py`, `test_gift_domain.py`, `test_referral_domain.py`, `test_start_token_dispatcher.py`, `test_billing_payments.py`, `test_owner_console_actions.py`, and `test_divination_handler.py`.

- [ ] **Step 2: If any pre-existing test set `package_credits` directly without a ledger row and now fails**

Such a test asserts counter behavior that the ledger-truth model changes. Fix it by creating an `AccountPackage` row (or calling `grant_credits`) instead of poking `package_credits`, mirroring the pattern in `test_consume_decrements_oldest_package_row`. Do NOT weaken a money assertion to make it pass — adjust the setup, not the expectation.

- [ ] **Step 3: Commit any test fixups**

```bash
git add tests/
git commit -m "test: align fixtures with ledger-as-source-of-truth"
```

---

## Self-Review

**Spec coverage (Workstream A — domain):**
- Source-of-truth model → Tasks 3-8 (grant_credits + rewire all four non-purchase sites + manual).
- Schema migration (nullable plan_id, source, backfill) → Tasks 1-2.
- Dead free-trial removal → Task 9.
- refund_quota row lock → Task 10.
- Divination ordering (bug #2) → Task 11.
- Handler enqueue-atomicity (#15) → explicitly deferred to the separate `A-handlers` plan (noted in Scope).

**Placeholder scan:** Tasks 5, 6, 7, 11 contain "confirm/adapt" notes rather than invented fakes — these are deliberate, because those test files have established doubles/constants the worker must reuse; the assertions and production code edits are fully specified. No `TODO`/`TBD` in production code steps.

**Type consistency:** `grant_credits(session, *, account_id, tenant_id, amount, source, expires_at=None, payment_id=None, plan_id=None)` is used identically in Tasks 3-8. `_sum_valid_packages(session, account_id)` and `_oldest_valid_package(session, account_id)` signatures match their definitions. `source` literals used: `welcome`, `gift`, `referral`, `manual`, `backfill`, `purchase` — consistent with the model comment in Task 1.
