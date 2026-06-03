# Referral & Subscription Integrity (Workstream B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make referral attribution and payout safe under concurrency and correctly tenant-scoped, and scope the subscription-renewal dedup lookup by tenant.

**Architecture:** Four independent fixes in the domain layer.
1. **Double payout** — `maybe_payout_referral` currently does read-then-write on `StartTokenUse.claimed_at`; two concurrent callers can both pay. Replace with an atomic `UPDATE ... SET claimed_at=now() WHERE id=:id AND claimed_at IS NULL` gate and only grant when `rowcount == 1`.
2. **Cross-tenant payment** — the "has any paid payment" check must be scoped by `token.tenant_id`.
3. **Double attribution** — `handle_referral_token` does read-then-insert; two concurrent `/start <ref>` clicks for the same referee can both insert. Serialize by `SELECT ... FOR UPDATE` on the referee's `Account` row before the existence check.
4. **Subscription dedup scoping** — `apply_subscription_payment`'s existing-subscription lookup must include `tenant_id`.

**Tech Stack:** SQLAlchemy async, Postgres row locking (`with_for_update`, `UPDATE ... WHERE`), pytest (`uv run pytest`), real per-worker test DB (commits are real; `_reset_state` truncates per test).

**Concurrency testing note:** the test DB is a real Postgres per xdist worker. To exercise a race, open two *independent* app sessions via `get_sessionmaker()` and run the two operations with `asyncio.gather`. Commit setup rows on the `session` fixture FIRST so the independent sessions can see them. Postgres row locking makes the outcomes deterministic (not flaky): the loser's gated `UPDATE` matches 0 rows / the loser's existence check sees the committed row. Example skeleton:

```python
from quantuum.db.session import get_sessionmaker

async def _worker(...):
    async with get_sessionmaker()() as s:
        # fetch fresh ORM objects in THIS session (never share across sessions)
        ...
        result = await some_domain_call(s, ...)
        await s.commit()
        return result

results = await asyncio.gather(_worker(...), _worker(...))
```

**Test command:** `uv run pytest <path> -v` (plain `pytest` fails). asyncio auto mode (no decorator); fixtures `session`, `default_tenant`.

---

### Task 1: Atomic referral-payout gate (double-payout fix)

**Files:**
- Modify: `src/quantuum/domain/referrals.py:168-233` (`maybe_payout_referral`)
- Test: `tests/test_referral_domain.py` (add a concurrency test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_referral_domain.py` (it already imports `maybe_payout_referral`, `generate_referral_code`, `_make_tenant`, `_make_account`, `_zero_balance`, `_mark_paid`, `StartTokenUse`, `AccountBalance`, `select`, `DEFAULT_REWARD_CREDITS`). Add `import asyncio` at the top if absent.

```python
async def test_maybe_payout_referral_concurrent_pays_once(session, default_tenant):
    from quantuum.db.session import get_sessionmaker

    referrer = await _make_account(session, default_tenant.id, 71001)
    referee = await _make_account(session, default_tenant.id, 72001)
    code = await generate_referral_code(
        session, account_id=referrer, tenant_id=default_tenant.id
    )
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await _zero_balance(session, referrer)
    await _mark_paid(session, tenant_id=default_tenant.id, account_id=referee)
    await session.commit()  # make setup visible to independent sessions

    async def _payout():
        async with get_sessionmaker()() as s:
            fired = await maybe_payout_referral(s, referee_account_id=referee)
            await s.commit()
            return fired

    results = await asyncio.gather(_payout(), _payout())

    assert sorted(results) == [False, True]  # exactly one payout fired
    bal = await session.get(AccountBalance, referrer)
    await session.refresh(bal)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS  # bumped exactly once

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().all()
    assert len(uses) == 1 and uses[0].claimed_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_referral_domain.py -k concurrent_pays_once -v`
Expected: FAIL — current read-then-write lets both callers pay (`results == [True, True]`, balance == 2× reward).

- [ ] **Step 3: Implement the atomic gate**

In `src/quantuum/domain/referrals.py`, add `update` to the sqlalchemy import:

```python
from sqlalchemy import exists, select, update
```

Replace the body of `maybe_payout_referral` from the `has_paid` block through the `return True` (lines ~192-233) with:

```python
    has_paid = (
        await session.execute(
            select(
                exists().where(
                    Payment.account_id == referee_account_id,
                    Payment.tenant_id == token.tenant_id,
                    Payment.status == "paid",
                )
            )
        )
    ).scalar()
    if not has_paid:
        return False

    # Atomic claim gate: only one concurrent caller wins the row. Under READ
    # COMMITTED the loser's UPDATE re-evaluates the WHERE after the winner
    # commits and matches 0 rows, so we never pay out twice.
    claim = await session.execute(
        update(StartTokenUse)
        .where(StartTokenUse.id == use.id, StartTokenUse.claimed_at.is_(None))
        .values(claimed_at=utcnow())
    )
    await session.flush()
    if claim.rowcount != 1:
        return False

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

NOTE: this removes the old `use.claimed_at = utcnow(); session.add(use)` lines — the atomic `UPDATE` now sets `claimed_at`. The `Payment.tenant_id == token.tenant_id` clause is Task 2's fix folded in here (it lives in the same `has_paid` block); keep it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_referral_domain.py -k concurrent_pays_once -v`
Expected: PASS

- [ ] **Step 5: Run the rest of the referral suite (no regressions)**

Run: `uv run pytest tests/test_referral_domain.py tests/test_consume_quota_referral_integration.py -v`
Expected: all PASS (the existing one-shot / happy-path / zero-reward tests still hold).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/referrals.py tests/test_referral_domain.py
git commit -m "fix(referrals): atomic payout claim gate prevents double payout"
```

---

### Task 2: Tenant-scope the referral payment check

**Files:**
- Modify: `src/quantuum/domain/referrals.py` (`has_paid` query — already edited in Task 1 to add `Payment.tenant_id == token.tenant_id`)
- Test: `tests/test_referral_domain.py` (add a tenant-scoping test)

NOTE: the production change for this task is the `Payment.tenant_id == token.tenant_id` clause, which Task 1 already added (it's in the same statement). This task adds the regression test that proves the scoping and guards against a future revert.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_referral_domain.py`. This seeds a paid Payment that belongs to a DIFFERENT tenant than the referral token, and asserts no payout fires.

```python
async def test_maybe_payout_referral_ignores_other_tenant_payment(session: AsyncSession):
    from quantuum.db.models import Payment

    t1 = await _make_tenant(session)
    t2 = Tenant(slug="t2", display_name="T2")
    session.add(t2)
    await session.flush()

    referrer = await _make_account(session, t1.id, 81001)
    referee = await _make_account(session, t1.id, 82001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t1.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await _zero_balance(session, referrer)
    # paid payment, but scoped to the WRONG tenant
    session.add(Payment(
        tenant_id=t2.id, account_id=referee, amount_cents=100,
        status="paid", paid_at=utcnow(),
    ))
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is False
    bal = await session.get(AccountBalance, referrer)
    assert bal is None or bal.package_credits == 0
```

NOTE: `Tenant` and `Payment` are imported in this file (check the imports; `Payment` already is). Add `from quantuum.db.models import Tenant` usage — `Tenant` is already imported (used by `_make_tenant`).

- [ ] **Step 2: Run test to verify it passes (Task 1 already added the fix)**

Run: `uv run pytest tests/test_referral_domain.py -k ignores_other_tenant_payment -v`
Expected: PASS (because Task 1 added the `Payment.tenant_id == token.tenant_id` clause).

IMPORTANT TDD CHECK: to confirm this test actually exercises the scoping, temporarily remove the `Payment.tenant_id == token.tenant_id` line, re-run — it must FAIL (fired becomes True). Then restore the line and re-run — it must PASS. Do this verification, then leave the fix in place.

- [ ] **Step 3: Commit**

```bash
git add tests/test_referral_domain.py
git commit -m "test(referrals): payout ignores paid payments from other tenants"
```

---

### Task 3: Serialize referral attribution (double-attribution fix)

**Files:**
- Modify: `src/quantuum/bot/handlers/start_tokens.py:73-108` (`handle_referral_token`)
- Test: `tests/test_start_token_dispatcher.py` (add a concurrency test)

- [ ] **Step 1: Inspect the existing test file**

Read `tests/test_start_token_dispatcher.py` to copy its setup helpers (how it builds a tenant, accounts, and a referral `StartToken`). Reuse those helpers in the new test.

- [ ] **Step 2: Write the failing test**

Add a concurrency test. Two independent sessions call `handle_referral_token` for the SAME referee concurrently; assert exactly one `StartTokenUse` row and `used_count == 1`.

```python
async def test_handle_referral_token_concurrent_attributes_once(session, default_tenant):
    import asyncio
    from quantuum.db.models import StartToken, StartTokenUse
    from quantuum.db.session import get_sessionmaker
    from quantuum.bot.handlers.start_tokens import handle_referral_token
    from sqlalchemy import select

    # referrer + referee accounts (reuse this file's account helper if present)
    from quantuum.auth.identity import find_or_create_account_by_tg
    referrer = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="attr_owner"
    )
    referee = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="attr_ee"
    )
    session.add(StartToken(
        code="attrcode1", kind="referral", tenant_id=default_tenant.id,
        owner_account_id=referrer.id, status="active",
    ))
    await session.commit()

    async def _attribute():
        async with get_sessionmaker()() as s:
            tok = await s.get(StartToken, "attrcode1")
            await handle_referral_token(s, token=tok, account_id=referee.id)
            await s.commit()

    await asyncio.gather(_attribute(), _attribute())

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee.id)
        )
    ).scalars().all()
    assert len(uses) == 1
    tok = await session.get(StartToken, "attrcode1")
    await session.refresh(tok)
    assert tok.used_count == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_start_token_dispatcher.py -k concurrent_attributes_once -v`
Expected: FAIL — current read-then-insert lets both callers insert (`len(uses) == 2`, `used_count == 2`).

- [ ] **Step 4: Implement the row lock**

In `src/quantuum/bot/handlers/start_tokens.py`, add `Account` to the models import:

```python
from quantuum.db.models import Account, StartToken, StartTokenUse
```

In `handle_referral_token`, immediately after the self-referral check and before the existence query, add:

```python
    # Serialize concurrent attributions for this referee: lock the account row
    # so the read-then-insert below cannot interleave with a second click.
    locked_acc = await session.get(Account, account_id, with_for_update=True)
    if locked_acc is None:
        return None
```

So the function reads:

```python
    if token.owner_account_id == account_id:
        return None
    locked_acc = await session.get(Account, account_id, with_for_update=True)
    if locked_acc is None:
        return None
    existing = await session.execute(
        select(StartTokenUse).where(StartTokenUse.account_id == account_id)
    )
    if existing.scalars().one_or_none() is not None:
        return None
    ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_start_token_dispatcher.py -k concurrent_attributes_once -v`
Expected: PASS

- [ ] **Step 6: Run the rest of the dispatcher suite**

Run: `uv run pytest tests/test_start_token_dispatcher.py tests/test_start_token_uses_no_unique.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/handlers/start_tokens.py tests/test_start_token_dispatcher.py
git commit -m "fix(referrals): lock account row to prevent double attribution"
```

---

### Task 4: Tenant-scope subscription renewal dedup

**Files:**
- Modify: `src/quantuum/domain/billing.py:157-164` (the existing-subscription lookup in `apply_subscription_payment`)
- Test: `tests/test_billing_crediting.py` (add a test; or whichever billing test file drives `apply_subscription_payment` — grep first)

- [ ] **Step 1: Locate the right test file**

Run: `grep -rln "apply_subscription_payment" tests/` and add the new test to the file that already drives subscription crediting (likely `tests/test_billing_crediting.py`). Mirror its setup helpers for tenant, account, and `SubscriptionPlan`.

- [ ] **Step 2: Write the failing test**

The test seeds an active `AccountSubscription` for the account that belongs to a DIFFERENT tenant but the same `plan_id`, then calls `apply_subscription_payment` for the account's real tenant. With the bug, the cross-tenant sub is renewed instead of a new one created.

```python
async def test_apply_subscription_payment_scopes_dedup_by_tenant(session, default_tenant):
    from datetime import timedelta
    from sqlalchemy import select
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import (
        Account, AccountSubscription, SubscriptionPlan, Tenant,
    )
    from quantuum.domain.billing import apply_subscription_payment

    other = Tenant(slug="other-sub", display_name="Other")
    session.add(other)
    await session.flush()

    acc = Account(tenant_id=default_tenant.id, tg_user_id=90001, role="user")
    session.add(acc)
    plan = SubscriptionPlan(
        tenant_id=default_tenant.id, name="Pro", price_cents=500,
        period_days=30, currency="XTR",
    )
    session.add(plan)
    await session.flush()

    # Pre-existing active sub for the SAME account+plan but the WRONG tenant.
    stale = AccountSubscription(
        tenant_id=other.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow(),
        ends_at=utcnow() + timedelta(days=30),
    )
    session.add(stale)
    await session.commit()

    await apply_subscription_payment(
        session, account_id=acc.id, tenant_id=default_tenant.id,
        plan=plan, payment_id=None,
    )

    subs = (
        await session.execute(
            select(AccountSubscription).where(AccountSubscription.account_id == acc.id)
        )
    ).scalars().all()
    # A new sub for the correct tenant must exist; the stale one is untouched.
    assert any(s.tenant_id == default_tenant.id for s in subs)
    assert len(subs) == 2
```

NOTE for implementer: adapt `SubscriptionPlan(...)` and `Account(...)` field names to the actual model columns (grep `class SubscriptionPlan` / `class Account` in `src/quantuum/db/models.py`). The contract is: after the call there are TWO subscriptions (the stale cross-tenant one + a new correct-tenant one), not one renewed cross-tenant sub.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest <billing test file> -k scopes_dedup_by_tenant -v`
Expected: FAIL — current lookup matches the cross-tenant sub and renews it, so `len(subs) == 1`.

- [ ] **Step 4: Implement**

In `src/quantuum/domain/billing.py`, in `apply_subscription_payment`, add the tenant filter to the lookup:

```python
    result = await session.execute(
        select(AccountSubscription).where(
            AccountSubscription.account_id == account_id,
            AccountSubscription.tenant_id == tenant_id,
            AccountSubscription.plan_id == plan.id,
            AccountSubscription.status.in_(("active", "grace")),
        )
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest <billing test file> -k scopes_dedup_by_tenant -v`
Expected: PASS

- [ ] **Step 6: Run the rest of the billing suite**

Run: `uv run pytest tests/test_billing_crediting.py tests/test_billing_fulfill.py tests/test_billing_grace.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/domain/billing.py <billing test file>
git commit -m "fix(billing): scope subscription renewal dedup by tenant"
```

---

### Task 5: Stage regression — full suite

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (prior baseline 2016 passed + the new tests from this plan).

- [ ] **Step 2: If anything fails**

Investigate. Do NOT weaken assertions. A likely cause if a referral test regresses: the old code set `claimed_at` on the ORM `use`; tests that asserted on the ORM object's `claimed_at` after a payout must now re-fetch (`await session.refresh(use)` or re-query) because the atomic `UPDATE` bypasses the identity map.

- [ ] **Step 3: No commit needed** unless a fix was made.

---

## Notes / scope

- The `StartTokenUse` unique-on-`account_id` constraint stays dropped (it's shared with gift tokens; a blanket unique would break gift claims). Concurrency safety comes from the app-level Account row lock (attribution) and the atomic claim `UPDATE` (payout), per the design spec's locked sub-decision.
- After this plan, update the `audit-fix-sweep-progress` memory: B DONE.
- Spec order is A → B → D → C → E → F → G; D (permissions & tenant scoping) is next.
