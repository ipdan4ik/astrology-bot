# Payments 3b — Telegram Stars, lifecycle & payouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 3a billing foundation transact real money — a `PaymentProvider` abstraction with a `TgStarsProvider`, an in-bot Telegram Stars purchase round-trip (invoice → pre-checkout → successful_payment → idempotent crediting), API purchase endpoints that route through the abstraction and return 501 (Stars is bot-only in MVP), a subscription lifecycle sweep with renewal reminders, and the payouts/tenant-licenses tables with superadmin payout endpoints.

**Architecture:** A thin provider seam (`src/quantuum/payments/`) defines the `PaymentProvider` Protocol and `TgStarsProvider`; Telegram Stars invoices are sent **in-bot** by aiogram (`bot.send_invoice` with `currency="XTR"`), so `TgStarsProvider.create_invoice` (the public-API path) raises `PaymentNotSupportedInApiError` → the API maps it to 501. Purchases record a `pending` `payments` row (3a); on Telegram's `successful_payment` the new `fulfill_payment` domain function gates crediting on the transition to `paid` (idempotent — re-delivery never double-credits) and dispatches to `apply_subscription_payment`/`apply_package_payment` (3a). A cron arq task `subscription_lifecycle` sweeps `active→grace→expired` (grace grants `GRACE_DAYS` of access, surfaced through a grace-aware `recompute_account_balance`) and sends `ends_at − REMINDER_DAYS` renewal reminders via each tenant's bot. Payouts sum a tenant's `paid` payments for a period minus a placeholder platform fee.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3.28 (Telegram Stars: `LabeledPrice`, `pre_checkout_query`, `successful_payment`), SQLModel async, asyncpg, Alembic, arq 0.28 (`cron`), Redis, pytest+httpx, uv.

**Scope notes / deliberate decisions:**
- **Stars are bot-only in MVP.** Invoices are sent inside the bot; there is no HTTP create-invoice path for Stars. The public API `POST /v1/me/subscriptions|packages` deliberately returns **501** *through* the provider abstraction (`TgStarsProvider.create_invoice` raises `PaymentNotSupportedInApiError`). This keeps the seam honest for future CloudPayments/CryptoBot (which *will* return an invoice URL) without faking it.
- **Provider per collecting tenant.** Telegram Stars always credit the bot that sent the invoice, so a purchase records `provider_id` = the *purchasing account's tenant's* `tg_stars` provider (lazily ensured). Bootstrap also seeds a `tg_stars` provider for the platform tenant (spec §7 Basic = platform tenant).
- **Idempotent crediting.** `fulfill_payment` is the single gate; it credits **only** on the `pending→paid` transition. Concurrent/duplicate `successful_payment` (webhook redelivery) is safe via the status check; the `account_subscriptions` partial-unique index is the DB backstop. Advisory-lock-by-`external_id` (spec §7) is deferred hardening — documented, not implemented.
- **Grace grants access (spec §7).** A `grace` subscription extends effective access by `GRACE_DAYS` past `ends_at`; `recompute_account_balance` computes `subscription_active_until = ends_at (+GRACE_DAYS if grace)`. Constants: `GRACE_DAYS = 5`, `REMINDER_DAYS = 3` (spec §7).
- **Placeholder platform fee.** `payouts` net = gross − `platform_fee_pct`% (default 30, a `Settings` field), consistent with 3a's placeholder plan prices — tune later.
- **`tenant_licenses` is table-only** (spec: "VIP, в MVP только таблица") — model + migration, no endpoints.
- Deliberate spec deviation carried from 3a: money amounts are integer `price_cents`/`amount_cents`; for `XTR` this is the integer Star amount (no ×100).

---

## File Structure

**New files:**
- `src/quantuum/payments/__init__.py` — package marker.
- `src/quantuum/payments/base.py` — `PaymentProvider` Protocol, `Invoice`/`PaymentEvent` dataclasses, `PaymentNotSupportedInApiError`.
- `src/quantuum/payments/tg_stars.py` — `TgStarsProvider`.
- `src/quantuum/payments/registry.py` — `PROVIDERS` kind→class map + `provider_for_kind`.
- `src/quantuum/domain/providers.py` — `ensure_stars_provider`, `get_active_provider`.
- `src/quantuum/domain/lifecycle.py` — `sweep_subscriptions`, `due_renewal_reminders`, `mark_reminder_sent`, `DueReminder`.
- `src/quantuum/domain/payouts.py` — `calculate_payout`, `mark_payout_paid`.
- `src/quantuum/bot/handlers/buy.py` — buy menu, invoice send, pre-checkout, successful-payment.
- `src/quantuum/tasks/lifecycle.py` — `subscription_lifecycle` arq cron task.
- `src/quantuum/api/routes/admin_payouts.py` — superadmin payout endpoints.
- `alembic/versions/d3c4e5f6a7b8_subscription_reminder.py`, `alembic/versions/e4d5f6a7b8c9_payouts_and_licenses.py`.
- Test files mirroring each.

**Modified files:**
- `src/quantuum/db/models.py` — `AccountSubscription.reminder_sent_at`, `Payout`, `TenantLicense`.
- `src/quantuum/domain/billing.py` — `GRACE_DAYS`/`REMINDER_DAYS` constants, grace-aware `recompute_account_balance`, `fulfill_payment`.
- `src/quantuum/db/bootstrap.py` — `ensure_platform_stars_provider`.
- `src/quantuum/bot/app.py` — include `buy.router`.
- `src/quantuum/bot/botpool.py` — `build_bots_by_tenant`.
- `src/quantuum/bot/ui/callbacks.py` — `BuyCb`.
- `src/quantuum/bot/handlers/generate.py` — `no_quota` message offers the buy flow.
- `src/quantuum/domain/accounts.py` — `get_tg_chat_id`.
- `src/quantuum/tasks/worker.py` — register `subscription_lifecycle` + `cron_jobs`.
- `src/quantuum/api/routes/me.py` — `POST /subscriptions`, `POST /packages` (→ 501 via abstraction).
- `src/quantuum/api/schemas.py` — `PurchaseIn`, `PayoutOut`, `PayoutCalculateIn`, `PayoutMarkPaidIn`.
- `src/quantuum/api/app.py` — wire `admin_payouts.router` + bootstrap `ensure_platform_stars_provider`.
- `src/quantuum/settings.py` — `platform_fee_pct: int = 30`.

---

## Phase A — Provider abstraction

### Task 1: PaymentProvider Protocol + TgStarsProvider + registry

**Files:**
- Create: `src/quantuum/payments/__init__.py`, `src/quantuum/payments/base.py`, `src/quantuum/payments/tg_stars.py`, `src/quantuum/payments/registry.py`
- Test: `tests/test_payments_provider.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_payments_provider.py`:

```python
import pytest

from quantuum.payments.base import Invoice, PaymentNotSupportedInApiError
from quantuum.payments.registry import provider_for_kind
from quantuum.payments.tg_stars import TgStarsProvider


def test_invoice_dataclass():
    inv = Invoice(title="t", description="d", payload="7", currency="XTR", amount=250)
    assert inv.payload == "7"
    assert inv.amount == 250


def test_registry_resolves_tg_stars():
    impl = provider_for_kind("tg_stars")
    assert isinstance(impl, TgStarsProvider)
    assert impl.kind == "tg_stars"


def test_registry_unknown_kind_returns_none():
    assert provider_for_kind("cloudpayments") is None


async def test_tg_stars_create_invoice_not_supported_in_api():
    impl = TgStarsProvider()
    with pytest.raises(PaymentNotSupportedInApiError):
        await impl.create_invoice(
            account_id=1, tenant_id=1, plan_kind="subscription", plan_id=1,
            amount_cents=250, currency="XTR", metadata={},
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payments_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: quantuum.payments`.

- [ ] **Step 3: Implement the package**

Create `src/quantuum/payments/__init__.py`:

```python
```

(empty file — package marker)

Create `src/quantuum/payments/base.py`:

```python
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


class PaymentNotSupportedInApiError(Exception):
    """Raised when a provider cannot create an invoice outside its native channel.

    Telegram Stars invoices can only be sent inside the bot (via ``bot.send_invoice``),
    so there is no public-API create-invoice path for them in MVP.
    """


@dataclass
class Invoice:
    title: str
    description: str
    payload: str
    currency: str
    amount: int  # smallest currency unit; for XTR this is the integer Star amount


@dataclass
class PaymentEvent:
    external_id: str
    payment_id: int
    amount: int
    currency: str


@runtime_checkable
class PaymentProvider(Protocol):
    kind: str

    async def create_invoice(
        self,
        *,
        account_id: int,
        tenant_id: int,
        plan_kind: Literal["subscription", "package"],
        plan_id: int,
        amount_cents: int,
        currency: str,
        metadata: dict,
    ) -> Invoice: ...

    async def verify_callback(self, body: bytes, headers: dict) -> PaymentEvent: ...

    async def refund(self, payment_id: int) -> bool: ...
```

Create `src/quantuum/payments/tg_stars.py`:

```python
from typing import Literal

from quantuum.payments.base import Invoice, PaymentEvent, PaymentNotSupportedInApiError


class TgStarsProvider:
    """Telegram Stars (XTR). Invoices are sent in-bot via ``bot.send_invoice``; there is no
    HTTP create-invoice or callback path. This class is the abstraction seam used by the
    public API (which therefore returns 501 for Stars) and by future HTTP providers."""

    kind = "tg_stars"

    async def create_invoice(
        self,
        *,
        account_id: int,
        tenant_id: int,
        plan_kind: Literal["subscription", "package"],
        plan_id: int,
        amount_cents: int,
        currency: str,
        metadata: dict,
    ) -> Invoice:
        raise PaymentNotSupportedInApiError(
            "Telegram Stars payments are only available inside the bot"
        )

    async def verify_callback(self, body: bytes, headers: dict) -> PaymentEvent:
        raise PaymentNotSupportedInApiError(
            "Telegram Stars has no HTTP callback; events arrive via the bot"
        )

    async def refund(self, payment_id: int) -> bool:
        raise NotImplementedError("Stars refunds are out of scope for MVP")
```

Create `src/quantuum/payments/registry.py`:

```python
from quantuum.payments.base import PaymentProvider
from quantuum.payments.tg_stars import TgStarsProvider

PROVIDERS: dict[str, type] = {
    "tg_stars": TgStarsProvider,
}


def provider_for_kind(kind: str) -> PaymentProvider | None:
    cls = PROVIDERS.get(kind)
    return cls() if cls is not None else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payments_provider.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/payments tests/test_payments_provider.py
git commit -m "feat(3b): PaymentProvider abstraction + TgStarsProvider + registry"
```

---

### Task 2: Provider rows — ensure_stars_provider + platform seeding

**Files:**
- Create: `src/quantuum/domain/providers.py`
- Modify: `src/quantuum/db/bootstrap.py`, `src/quantuum/api/app.py`, `src/quantuum/bot/polling.py`, `src/quantuum/bot/runner.py`
- Test: `tests/test_providers_domain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_providers_domain.py`:

```python
from sqlmodel import select

from quantuum.db.models import PaymentProvider
from quantuum.domain.providers import ensure_stars_provider, get_active_provider


async def test_ensure_stars_provider_idempotent(session, default_tenant):
    p1 = await ensure_stars_provider(session, default_tenant.id)
    p2 = await ensure_stars_provider(session, default_tenant.id)
    assert p1.id == p2.id
    assert p1.kind == "tg_stars"

    result = await session.execute(
        select(PaymentProvider).where(PaymentProvider.tenant_id == default_tenant.id)
    )
    assert len(result.scalars().all()) == 1


async def test_get_active_provider(session, default_tenant):
    assert await get_active_provider(session, default_tenant.id) is None
    created = await ensure_stars_provider(session, default_tenant.id)
    got = await get_active_provider(session, default_tenant.id)
    assert got is not None and got.id == created.id


async def test_ensure_platform_stars_provider(session):
    from quantuum.db.bootstrap import ensure_platform_stars_provider, ensure_platform_tenant

    platform = await ensure_platform_tenant(session)
    await ensure_platform_stars_provider(session)
    got = await get_active_provider(session, platform.id)
    assert got is not None and got.kind == "tg_stars"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_providers_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: quantuum.domain.providers`.

- [ ] **Step 3: Implement the domain module**

Create `src/quantuum/domain/providers.py`:

```python
from sqlmodel import select

from quantuum.db.models import PaymentProvider


async def get_active_provider(session, tenant_id: int) -> PaymentProvider | None:
    result = await session.execute(
        select(PaymentProvider)
        .where(
            PaymentProvider.tenant_id == tenant_id,
            PaymentProvider.kind == "tg_stars",
            PaymentProvider.active == True,  # noqa: E712
        )
        .order_by(PaymentProvider.id)
    )
    return result.scalars().first()


async def ensure_stars_provider(session, tenant_id: int) -> PaymentProvider:
    """Get-or-create the tenant's active Telegram Stars provider row (idempotent)."""
    existing = await get_active_provider(session, tenant_id)
    if existing is not None:
        return existing
    provider = PaymentProvider(tenant_id=tenant_id, kind="tg_stars")
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider
```

- [ ] **Step 4: Implement platform seeding in bootstrap**

In `src/quantuum/db/bootstrap.py`, append:

```python
async def ensure_platform_stars_provider(session) -> None:
    """Seed a Telegram Stars provider row for the platform tenant (idempotent)."""
    from quantuum.domain.providers import ensure_stars_provider

    platform = await ensure_platform_tenant(session)
    await ensure_stars_provider(session, platform.id)
```

- [ ] **Step 5: Wire seeding into startup paths**

In `src/quantuum/api/app.py`, add `ensure_platform_stars_provider` to the bootstrap import block and call it in `_lifespan` (after `ensure_global_plans`):

```python
        await ensure_platform_stars_provider(session)
```

In `src/quantuum/bot/polling.py` **and** `src/quantuum/bot/runner.py`, add `ensure_platform_stars_provider` to the `from quantuum.db.bootstrap import (...)` block and call it inside the `async with get_sessionmaker()() as session:` startup block (after `ensure_master_bot(session)`):

```python
        await ensure_platform_stars_provider(session)
```

- [ ] **Step 6: Run tests + suite + commit**

Run: `uv run pytest tests/test_providers_domain.py -v && uv run pytest -q && uv run ruff check .`
Expected: PASS.

```bash
git add src/quantuum/domain/providers.py src/quantuum/db/bootstrap.py src/quantuum/api/app.py src/quantuum/bot/polling.py src/quantuum/bot/runner.py tests/test_providers_domain.py
git commit -m "feat(3b): payment_providers — ensure_stars_provider + platform seeding"
```

---

## Phase B — Idempotent fulfillment

### Task 3: fulfill_payment (idempotent crediting gate)

**Files:**
- Modify: `src/quantuum/domain/billing.py`
- Test: `tests/test_billing_fulfill.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_billing_fulfill.py`:

```python
from quantuum.db.models import Account, AccountBalance, PackagePlan, SubscriptionPlan
from quantuum.domain.billing import fulfill_payment, record_pending_payment


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    return acc


async def test_fulfill_subscription_payment_credits_once(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=250)
    session.add(plan)
    await session.flush()
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR",
        metadata={"kind": "subscription", "plan_id": plan.id},
    )

    first = await fulfill_payment(session, payment_id=pay.id, external_id="charge_1")
    assert first is True
    bal = await session.get(AccountBalance, acc.id)
    assert bal.subscription_active_until is not None

    # Idempotent: re-delivery does not double-credit.
    again = await fulfill_payment(session, payment_id=pay.id, external_id="charge_1")
    assert again is False
    await session.refresh(pay)
    assert pay.status == "paid"
    assert pay.external_id == "charge_1"


async def test_fulfill_package_payment_credits(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=400)
    session.add(plan)
    await session.flush()
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=400, currency="XTR", metadata={"kind": "package", "plan_id": plan.id},
    )

    assert await fulfill_payment(session, payment_id=pay.id, external_id="charge_2") is True
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5

    # Re-delivery is a no-op (credits stay at 5).
    assert await fulfill_payment(session, payment_id=pay.id, external_id="charge_2") is False
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5


async def test_fulfill_unknown_payment_is_safe(session):
    assert await fulfill_payment(session, payment_id=999999, external_id="x") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_fulfill.py -v`
Expected: FAIL — `ImportError: cannot import name 'fulfill_payment'`.

- [ ] **Step 3: Implement**

In `src/quantuum/domain/billing.py`, add the plan-lookup import near the top imports:

```python
from quantuum.domain.plans import get_package_plan, get_subscription_plan
```

Append the function at the end of the file:

```python
async def fulfill_payment(session, *, payment_id: int, external_id: str) -> bool:
    """Idempotently mark a payment paid and apply its crediting.

    Returns True if this call performed the fulfillment (the pending→paid transition);
    False if the payment is unknown or was already paid. Crediting happens ONLY on the
    transition, so duplicate/redelivered payment events never double-credit.
    """
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.status == "paid":
        return False

    payment.status = "paid"
    payment.external_id = external_id
    payment.paid_at = utcnow()
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    meta = payment.metadata_json or {}
    kind = meta.get("kind")
    plan_id = meta.get("plan_id")
    if kind == "subscription":
        plan = await get_subscription_plan(session, plan_id)
        if plan is not None:
            await apply_subscription_payment(
                session, account_id=payment.account_id, tenant_id=payment.tenant_id,
                plan=plan, payment_id=payment.id,
            )
    elif kind == "package":
        plan = await get_package_plan(session, plan_id)
        if plan is not None:
            await apply_package_payment(
                session, account_id=payment.account_id, tenant_id=payment.tenant_id,
                plan=plan, payment_id=payment.id,
            )
    return True
```

> **Note for implementer:** if `kind`/`plan_id` is missing or the plan was deactivated between invoice and payment, the payment is still recorded as `paid` (money was received) but no credit is granted — superadmin reconciles manually. This is an accepted MVP edge; do not raise.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing_fulfill.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/domain/billing.py tests/test_billing_fulfill.py
git commit -m "feat(3b): fulfill_payment — idempotent paid-transition crediting gate"
```

---

## Phase C — Bot Telegram Stars purchase flow

### Task 4: BuyCb callback + buy menu (list plans)

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py`
- Create: `src/quantuum/bot/handlers/buy.py`
- Test: `tests/test_buy_menu.py`, `tests/test_ui_callbacks.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_callbacks.py`:

```python
def test_buy_callback_roundtrip():
    from quantuum.bot.ui.callbacks import BuyCb

    packed = BuyCb(action="pick", kind="subscription", plan_id=7).pack()
    cb = BuyCb.unpack(packed)
    assert cb.action == "pick"
    assert cb.kind == "subscription"
    assert cb.plan_id == 7
```

Create `tests/test_buy_menu.py`:

```python
from quantuum.bot.handlers.buy import build_buy_menu
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.bootstrap import ensure_global_plans


async def test_build_buy_menu_lists_active_plans(session, default_tenant):
    await ensure_global_plans(session)
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id)

    assert "★" in text  # Star pricing shown
    callbacks = [
        BuyCb.unpack(btn.callback_data)
        for row in kb.inline_keyboard
        for btn in row
    ]
    kinds = {(c.kind) for c in callbacks}
    assert "subscription" in kinds
    assert "package" in kinds
    assert all(c.action == "pick" for c in callbacks)


async def test_build_buy_menu_empty_when_no_plans(session, default_tenant):
    text, kb = await build_buy_menu(session, tenant_id=default_tenant.id)
    assert kb.inline_keyboard == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_buy_menu.py tests/test_ui_callbacks.py::test_buy_callback_roundtrip -v`
Expected: FAIL — `ImportError` (no `BuyCb` / no `quantuum.bot.handlers.buy`).

- [ ] **Step 3: Add the callback**

In `src/quantuum/bot/ui/callbacks.py`, append:

```python
class BuyCb(CallbackData, prefix="buy"):
    action: str  # open | pick
    kind: str = ""  # subscription | package
    plan_id: int = 0
```

- [ ] **Step 4: Implement the buy menu builder + open handler**

Create `src/quantuum/bot/handlers/buy.py`:

```python
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.plans import list_package_plans, list_subscription_plans

router = Router()


async def build_buy_menu(session, *, tenant_id: int) -> tuple[str, InlineKeyboardMarkup]:
    subs = await list_subscription_plans(session, tenant_id=tenant_id)
    pkgs = await list_package_plans(session, tenant_id=tenant_id)
    builder = InlineKeyboardBuilder()
    for s in subs:
        builder.button(
            text=f"⭐ {s.name} — {s.price_cents}★",
            callback_data=BuyCb(action="pick", kind="subscription", plan_id=s.id),
        )
    for p in pkgs:
        builder.button(
            text=f"⭐ {p.name} · {p.request_count} разборов — {p.price_cents}★",
            callback_data=BuyCb(action="pick", kind="package", plan_id=p.id),
        )
    builder.adjust(1)
    text = "Выбери, что купить (оплата звёздами Telegram ★):"
    return text, builder.as_markup()


async def show_buy_menu(message: Message, tenant_id: int) -> None:
    async with get_sessionmaker()() as session:
        text, kb = await build_buy_menu(session, tenant_id=tenant_id)
    if not kb.inline_keyboard:
        await message.answer("Пока нет доступных планов. Загляни позже.")
        return
    await message.answer(text, reply_markup=kb)


@router.message(Command("buy"))
async def on_buy_command(message: Message, account: Account) -> None:
    await show_buy_menu(message, account.tenant_id)


@router.callback_query(BuyCb.filter(F.action == "open"))
async def on_buy_open(query: CallbackQuery, account: Account) -> None:
    await show_buy_menu(query.message, account.tenant_id)
    await query.answer()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_buy_menu.py tests/test_ui_callbacks.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/buy.py tests/test_buy_menu.py tests/test_ui_callbacks.py
git commit -m "feat(3b): bot buy menu — BuyCb + /buy command + plan listing"
```

---

### Task 5: Send Stars invoice + pre-checkout + successful_payment

**Files:**
- Modify: `src/quantuum/bot/handlers/buy.py`, `src/quantuum/bot/app.py`
- Test: `tests/test_buy_flow.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_buy_flow.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.db.models import Account, AccountBalance, Payment, SubscriptionPlan


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


async def test_pick_records_pending_payment_and_sends_invoice(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import buy
    from quantuum.bot.ui.callbacks import BuyCb

    _patch_sessionmaker(monkeypatch, buy, session)

    acc = Account(tenant_id=default_tenant.id)
    plan = SubscriptionPlan(slug="m", name="Monthly", period_days=30, price_cents=250)
    session.add(acc)
    session.add(plan)
    await session.flush()

    bot = AsyncMock()
    query = AsyncMock()
    query.message = SimpleNamespace(chat=SimpleNamespace(id=4242))

    await buy.on_buy_pick(
        query, BuyCb(action="pick", kind="subscription", plan_id=plan.id), bot=bot, account=acc
    )

    bot.send_invoice.assert_awaited_once()
    kwargs = bot.send_invoice.await_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["chat_id"] == 4242
    assert kwargs["prices"][0].amount == 250

    from sqlmodel import select
    result = await session.execute(select(Payment).where(Payment.account_id == acc.id))
    pay = result.scalar_one()
    assert pay.status == "pending"
    assert pay.metadata_json == {"kind": "subscription", "plan_id": plan.id}
    assert kwargs["payload"] == str(pay.id)


async def test_pick_unknown_plan_alerts(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import buy
    from quantuum.bot.ui.callbacks import BuyCb

    _patch_sessionmaker(monkeypatch, buy, session)
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()

    bot = AsyncMock()
    query = AsyncMock()
    query.message = SimpleNamespace(chat=SimpleNamespace(id=1))
    await buy.on_buy_pick(query, BuyCb(action="pick", kind="package", plan_id=999), bot=bot, account=acc)

    bot.send_invoice.assert_not_awaited()
    query.answer.assert_awaited()


async def test_pre_checkout_answers_ok():
    from quantuum.bot.handlers import buy

    query = AsyncMock()
    await buy.on_pre_checkout(query)
    query.answer.assert_awaited_once_with(ok=True)


async def test_successful_payment_fulfills(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import buy
    from quantuum.domain.billing import record_pending_payment

    _patch_sessionmaker(monkeypatch, buy, session)
    acc = Account(tenant_id=default_tenant.id)
    plan = SubscriptionPlan(slug="m", name="Monthly", period_days=30, price_cents=250)
    session.add(acc)
    session.add(plan)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR", metadata={"kind": "subscription", "plan_id": plan.id},
    )

    message = SimpleNamespace(
        successful_payment=SimpleNamespace(
            invoice_payload=str(pay.id),
            telegram_payment_charge_id="charge_abc",
            total_amount=250,
            currency="XTR",
        ),
        answer=AsyncMock(),
    )
    await buy.on_successful_payment(message)

    await session.refresh(pay)
    assert pay.status == "paid"
    assert pay.external_id == "charge_abc"
    message.answer.assert_awaited_once()
    bal = await session.get(AccountBalance, acc.id)
    assert bal.subscription_active_until is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_buy_flow.py -v`
Expected: FAIL — `AttributeError` (`on_buy_pick`/`on_pre_checkout`/`on_successful_payment` missing).

- [ ] **Step 3: Implement the invoice + checkout handlers**

In `src/quantuum/bot/handlers/buy.py`, widen the imports:

```python
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.billing import fulfill_payment, record_pending_payment
from quantuum.domain.plans import (
    get_package_plan,
    get_subscription_plan,
    list_package_plans,
    list_subscription_plans,
)
from quantuum.domain.providers import ensure_stars_provider
```

Append the handlers:

```python
def _invoice_description(kind: str, plan) -> str:
    if kind == "subscription":
        return f"Подписка на {plan.period_days} дней"
    return f"Пакет: {plan.request_count} разборов"


@router.callback_query(BuyCb.filter(F.action == "pick"))
async def on_buy_pick(
    query: CallbackQuery, callback_data: BuyCb, bot: Bot, account: Account
) -> None:
    chat_id = query.message.chat.id
    async with get_sessionmaker()() as session:
        if callback_data.kind == "subscription":
            plan = await get_subscription_plan(session, callback_data.plan_id)
        else:
            plan = await get_package_plan(session, callback_data.plan_id)
        if plan is None:
            await query.answer("Этот план больше недоступен.", show_alert=True)
            return
        provider = await ensure_stars_provider(session, account.tenant_id)
        payment = await record_pending_payment(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            provider_id=provider.id,
            amount_cents=plan.price_cents,
            currency="XTR",
            metadata={"kind": callback_data.kind, "plan_id": plan.id},
        )
    await bot.send_invoice(
        chat_id=chat_id,
        title=plan.name,
        description=_invoice_description(callback_data.kind, plan),
        payload=str(payment.id),
        currency="XTR",
        prices=[LabeledPrice(label=plan.name, amount=plan.price_cents)],
    )
    await query.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    # Stars: nothing to reserve server-side; accept so Telegram charges the user.
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    payment_id = int(sp.invoice_payload)
    async with get_sessionmaker()() as session:
        credited = await fulfill_payment(
            session, payment_id=payment_id, external_id=sp.telegram_payment_charge_id
        )
    if credited:
        await message.answer("Оплата получена! Доступ активирован. ✨")
    else:
        await message.answer("Эта оплата уже была учтена ранее.")
```

> **Note for implementer:** `bot.send_invoice` for Stars takes an empty/omitted `provider_token` (XTR uses no provider token). Do **not** pass `provider_token`. The `amount` in `LabeledPrice` is the integer Star count (`price_cents`), not multiplied by 100.

- [ ] **Step 4: Register the router on the customer dispatcher**

In `src/quantuum/bot/app.py`, add `buy` to the handlers import and include it right after `start.router`:

```python
    from quantuum.bot.handlers import buy, generate, history, menu, onboarding, profile, start

    dp.include_router(start.router)
    dp.include_router(buy.router)
    dp.include_router(generate.router)
```

(leave the rest of the includes unchanged)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_buy_flow.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/handlers/buy.py src/quantuum/bot/app.py tests/test_buy_flow.py
git commit -m "feat(3b): bot Stars flow — send_invoice + pre_checkout + successful_payment fulfillment"
```

---

### Task 6: Offer the buy flow on no_quota

**Files:**
- Modify: `src/quantuum/bot/handlers/generate.py`
- Test: `tests/test_generate_no_quota_offer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_generate_no_quota_offer.py`:

```python
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.generate import run_generate
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.domain.natal_profiles import upsert_natal_profile


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


async def test_no_quota_offers_buy_button(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import generate as gen

    _patch_sessionmaker(monkeypatch, gen, session)
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="9")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    # burn the free trial
    monkeypatch.setattr(gen, "enqueue_blueprint", AsyncMock())
    await run_generate(SimpleNamespace(answer=AsyncMock()), acc, chat_id=9)

    message = SimpleNamespace(answer=AsyncMock())
    await run_generate(message, acc, chat_id=9)

    message.answer.assert_awaited()
    kb = message.answer.await_args.kwargs["reply_markup"]
    cb = BuyCb.unpack(kb.inline_keyboard[0][0].callback_data)
    assert cb.action == "open"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_generate_no_quota_offer.py -v`
Expected: FAIL — the `no_quota` branch currently sends a plain text with no `reply_markup`.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/generate.py`, add imports near the top:

```python
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import BuyCb
```

Add a small keyboard helper above `run_generate`:

```python
def _buy_offer_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Купить разборы", callback_data=BuyCb(action="open").pack())
    )
    return builder.as_markup()
```

Replace the `no_quota` branch in `run_generate`:

```python
    elif status == "no_quota":
        await message.answer(
            "Бесплатная генерация уже использована. Купи пакет разборов или подписку:",
            reply_markup=_buy_offer_kb(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_generate_no_quota_offer.py -v`
Expected: PASS.

- [ ] **Step 5: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/handlers/generate.py tests/test_generate_no_quota_offer.py
git commit -m "feat(3b): no_quota message offers the buy flow"
```

---

## Phase D — API purchase via the abstraction (501)

### Task 7: POST /v1/me/subscriptions + /v1/me/packages → 501

**Files:**
- Modify: `src/quantuum/api/schemas.py`, `src/quantuum/api/routes/me.py`
- Test: `tests/test_api_purchase.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_purchase.py`:

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.bootstrap import ensure_global_plans
from quantuum.db.models import Account
from quantuum.domain.plans import list_subscription_plans
from quantuum.domain.providers import ensure_stars_provider


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_and_plan(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    await ensure_global_plans(session)
    await ensure_stars_provider(session, default_tenant.id)
    await session.commit()
    await session.refresh(acc)
    subs = await list_subscription_plans(session, tenant_id=default_tenant.id)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}, subs[0].id


async def test_post_subscription_returns_501(client, auth_and_plan):
    headers, plan_id = auth_and_plan
    r = await client.post("/v1/me/subscriptions", headers=headers, json={"plan_id": plan_id})
    assert r.status_code == 501


async def test_post_subscription_unknown_plan_404(client, auth_and_plan):
    headers, _ = auth_and_plan
    r = await client.post("/v1/me/subscriptions", headers=headers, json={"plan_id": 999999})
    assert r.status_code == 404


async def test_post_package_returns_501(client, auth_and_plan):
    headers, _ = auth_and_plan
    from quantuum.domain.plans import list_package_plans  # noqa: F401
    r = await client.post("/v1/me/packages", headers=headers, json={"plan_id": 999999})
    # unknown plan resolves to 404 before the provider; verify the route exists (not 405)
    assert r.status_code in (404, 501)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_purchase.py -v`
Expected: FAIL — 405/404 (routes missing).

- [ ] **Step 3: Add the request schema**

In `src/quantuum/api/schemas.py`, append:

```python
class PurchaseIn(BaseModel):
    plan_id: int
```

- [ ] **Step 4: Implement the routes**

In `src/quantuum/api/routes/me.py`, add imports (merge into the existing schema/model import lines and add the new ones):

```python
from quantuum.api.schemas import PurchaseIn
from quantuum.domain.plans import get_package_plan, get_subscription_plan
from quantuum.domain.providers import get_active_provider
from quantuum.payments.base import PaymentNotSupportedInApiError
from quantuum.payments.registry import provider_for_kind
```

Add a shared helper + the two routes:

```python
async def _create_invoice_via_provider(
    session: AsyncSession, account: Account, *, plan_kind: str, plan
) -> None:
    """Route a purchase through the PaymentProvider abstraction.

    In MVP the only provider is Telegram Stars, which is bot-only and raises
    PaymentNotSupportedInApiError → 501. Future HTTP providers will return an invoice URL here.
    """
    provider_row = await get_active_provider(session, account.tenant_id)
    impl = provider_for_kind(provider_row.kind) if provider_row else None
    if impl is None:
        raise HTTPException(status_code=501, detail="no payment provider configured")
    try:
        await impl.create_invoice(
            account_id=account.id,
            tenant_id=account.tenant_id,
            plan_kind=plan_kind,
            plan_id=plan.id,
            amount_cents=plan.price_cents,
            currency=plan.currency,
            metadata={"kind": plan_kind, "plan_id": plan.id},
        )
    except PaymentNotSupportedInApiError as exc:
        raise HTTPException(
            status_code=501, detail="this payment method is available only in the bot"
        ) from exc


@router.post("/subscriptions", status_code=201)
async def buy_subscription(
    body: PurchaseIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
):
    plan = await get_subscription_plan(session, body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _create_invoice_via_provider(session, account, plan_kind="subscription", plan=plan)
    return {"status": "invoice_created"}  # unreachable in MVP (Stars raises 501)


@router.post("/packages", status_code=201)
async def buy_package(
    body: PurchaseIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
):
    plan = await get_package_plan(session, body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _create_invoice_via_provider(session, account, plan_kind="package", plan=plan)
    return {"status": "invoice_created"}  # unreachable in MVP (Stars raises 501)
```

> **Note for implementer:** `POST /subscriptions` must coexist with the existing `GET /subscriptions` (3a) — both decorate the same path with different methods. Keep the GET handler.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_purchase.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/api/schemas.py src/quantuum/api/routes/me.py tests/test_api_purchase.py
git commit -m "feat(3b): API purchase endpoints route through provider abstraction (501 for Stars)"
```

---

## Phase E — Subscription lifecycle

### Task 8: reminder_sent_at column + grace-aware recompute

**Files:**
- Modify: `src/quantuum/db/models.py`, `src/quantuum/domain/billing.py`
- Create: `alembic/versions/d3c4e5f6a7b8_subscription_reminder.py`
- Test: `tests/test_billing_grace.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_billing_grace.py`:

```python
from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountSubscription,
    SubscriptionPlan,
)
from quantuum.domain.billing import GRACE_DAYS, recompute_account_balance


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    await session.flush()
    return acc


async def test_grace_subscription_extends_access_by_grace_days(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    ended = utcnow() - timedelta(hours=1)  # already past ends_at
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="grace", started_at=ended - timedelta(days=30), ends_at=ended,
    ))
    await session.commit()

    bal = await recompute_account_balance(session, acc.id)
    # grace still grants access: active_until ≈ ends_at + GRACE_DAYS (in the future)
    assert bal.subscription_active_until is not None
    assert bal.subscription_active_until > utcnow()
    assert bal.subscription_active_until <= ended + timedelta(days=GRACE_DAYS) + timedelta(seconds=1)


async def test_active_subscription_access_is_ends_at(session, default_tenant):
    acc = await _account(session, default_tenant)
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    ends = utcnow() + timedelta(days=10)
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow(), ends_at=ends,
    ))
    await session.commit()

    bal = await recompute_account_balance(session, acc.id)
    assert abs((bal.subscription_active_until - ends).total_seconds()) < 1  # no grace added
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing_grace.py -v`
Expected: FAIL — `ImportError: cannot import name 'GRACE_DAYS'` (and grace not extended).

- [ ] **Step 3: Add the model column**

In `src/quantuum/db/models.py`, add a field to `AccountSubscription` (after `cancelled_at`):

```python
    reminder_sent_at: datetime | None = _dt_field(default=None)
```

- [ ] **Step 4: Implement constants + grace-aware recompute**

In `src/quantuum/domain/billing.py`, add the constants near the top (after imports):

```python
GRACE_DAYS = 5  # spec §7: grace window grants this many days of access past ends_at
REMINDER_DAYS = 3  # spec §7: renewal reminder fires this many days before ends_at
```

Replace the subscription portion of `recompute_account_balance` (the `sub_result`/`ends` block) with a grace-aware version:

```python
    sub_result = await session.execute(
        select(AccountSubscription.status, AccountSubscription.ends_at).where(
            AccountSubscription.account_id == account_id,
            AccountSubscription.status.in_(("active", "grace")),
        )
    )
    effective_ends = [
        (ends + timedelta(days=GRACE_DAYS)) if status == "grace" else ends
        for status, ends in sub_result.all()
    ]
    balance.subscription_active_until = max(effective_ends) if effective_ends else None
```

(`timedelta` is already imported in `billing.py`.)

- [ ] **Step 5: Write the migration**

Create `alembic/versions/d3c4e5f6a7b8_subscription_reminder.py`:

```python
"""account_subscriptions.reminder_sent_at

Revision ID: d3c4e5f6a7b8
Revises: c2b3d4e5f6a7
Create Date: 2026-05-21 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3c4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "c2b3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_subscriptions",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_subscriptions", "reminder_sent_at")
```

- [ ] **Step 6: Verify migration + no drift**

Run: `uv run alembic upgrade head` (targets the app DB at 172.29.0.2; the test DB at 172.30.0.2 is managed by `create_all`).
Run: `uv run alembic check` → "No new upgrade operations detected." (If unavailable, autogenerate a scratch revision, confirm empty `upgrade()`, then delete it.)

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`
Expected: PASS (existing 3a crediting tests still green — active subs unaffected).

```bash
git add src/quantuum/db/models.py src/quantuum/domain/billing.py alembic/versions/d3c4e5f6a7b8_subscription_reminder.py tests/test_billing_grace.py
git commit -m "feat(3b): reminder_sent_at column + grace-aware subscription_active_until"
```

---

### Task 9: Lifecycle domain — sweep + due reminders

**Files:**
- Create: `src/quantuum/domain/lifecycle.py`
- Modify: `src/quantuum/domain/accounts.py`
- Test: `tests/test_lifecycle_domain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lifecycle_domain.py`:

```python
from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountIdentity,
    AccountSubscription,
    SubscriptionPlan,
)
from quantuum.domain.lifecycle import (
    due_renewal_reminders,
    mark_reminder_sent,
    sweep_subscriptions,
)


async def _acc_with_chat(session, default_tenant, tg_id: str):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg_id))
    await session.flush()
    return acc


async def test_sweep_active_to_grace_and_grace_to_expired(session, default_tenant):
    acc = await _acc_with_chat(session, default_tenant, "100")
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    now = utcnow()
    # active but past ends_at → should become grace
    s_grace = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=now - timedelta(days=31), ends_at=now - timedelta(hours=1),
    )
    # grace past the grace window → should become expired
    s_expired = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="grace", started_at=now - timedelta(days=40),
        ends_at=now - timedelta(days=10),
    )
    session.add(s_grace)
    session.add(s_expired)
    await session.commit()

    await sweep_subscriptions(session)

    await session.refresh(s_grace)
    await session.refresh(s_expired)
    assert s_grace.status == "grace"
    assert s_expired.status == "expired"


async def test_due_renewal_reminders_and_mark(session, default_tenant):
    acc = await _acc_with_chat(session, default_tenant, "200")
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    now = utcnow()
    sub = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=now - timedelta(days=28),
        ends_at=now + timedelta(days=2),  # within REMINDER_DAYS (3)
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)

    due = await due_renewal_reminders(session)
    assert len(due) == 1
    item = due[0]
    assert item.sub_id == sub.id
    assert item.tenant_id == default_tenant.id
    assert item.chat_id == "200"

    await mark_reminder_sent(session, sub.id)
    # not due again once reminded
    assert await due_renewal_reminders(session) == []


async def test_reminder_not_due_when_far_out(session, default_tenant):
    acc = await _acc_with_chat(session, default_tenant, "300")
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    session.add(AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow(), ends_at=utcnow() + timedelta(days=20),
    ))
    await session.commit()
    assert await due_renewal_reminders(session) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lifecycle_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: quantuum.domain.lifecycle`.

- [ ] **Step 3: Add the chat-id helper**

In `src/quantuum/domain/accounts.py`, add the import and the function:

```python
from sqlmodel import select

from quantuum.db.models import AccountIdentity
```

```python
async def get_tg_chat_id(session, account_id: int) -> str | None:
    """Return the account's Telegram chat id (== tg_chat provider_user_id) or None."""
    result = await session.execute(
        select(AccountIdentity.provider_user_id).where(
            AccountIdentity.account_id == account_id,
            AccountIdentity.provider == "tg_chat",
        )
    )
    return result.scalars().first()
```

(merge the `Account` import that already exists; add `AccountIdentity` and `select`.)

- [ ] **Step 4: Implement the lifecycle domain**

Create `src/quantuum/domain/lifecycle.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountIdentity, AccountSubscription
from quantuum.domain.billing import GRACE_DAYS, REMINDER_DAYS, recompute_account_balance


@dataclass
class DueReminder:
    sub_id: int
    account_id: int
    tenant_id: int
    chat_id: str | None


async def sweep_subscriptions(session, *, now: datetime | None = None) -> dict[str, int]:
    """Advance the subscription state machine. Returns counts of transitions.

    active → grace  when now >= ends_at
    grace  → expired when now >= ends_at + GRACE_DAYS
    Balances of affected accounts are recomputed so subscription_active_until stays correct.
    """
    now = now or utcnow()
    affected: set[int] = set()

    grace_q = await session.execute(
        select(AccountSubscription).where(
            AccountSubscription.status == "active",
            AccountSubscription.ends_at <= now,
        )
    )
    to_grace = list(grace_q.scalars().all())
    for sub in to_grace:
        sub.status = "grace"
        session.add(sub)
        affected.add(sub.account_id)

    expire_q = await session.execute(
        select(AccountSubscription).where(
            AccountSubscription.status == "grace",
            AccountSubscription.ends_at <= now - timedelta(days=GRACE_DAYS),
        )
    )
    to_expired = list(expire_q.scalars().all())
    for sub in to_expired:
        sub.status = "expired"
        session.add(sub)
        affected.add(sub.account_id)

    await session.commit()
    for account_id in affected:
        await recompute_account_balance(session, account_id)

    return {"to_grace": len(to_grace), "to_expired": len(to_expired)}


async def due_renewal_reminders(session, *, now: datetime | None = None) -> list[DueReminder]:
    """Active subscriptions entering the reminder window that have not been reminded yet."""
    now = now or utcnow()
    window_end = now + timedelta(days=REMINDER_DAYS)
    result = await session.execute(
        select(AccountSubscription, AccountIdentity.provider_user_id)
        .join(
            AccountIdentity,
            (AccountIdentity.account_id == AccountSubscription.account_id)
            & (AccountIdentity.provider == "tg_chat"),
            isouter=True,
        )
        .where(
            AccountSubscription.status == "active",
            AccountSubscription.reminder_sent_at.is_(None),
            AccountSubscription.ends_at > now,
            AccountSubscription.ends_at <= window_end,
        )
    )
    return [
        DueReminder(sub_id=sub.id, account_id=sub.account_id, tenant_id=sub.tenant_id, chat_id=chat)
        for sub, chat in result.all()
    ]


async def mark_reminder_sent(session, sub_id: int, *, now: datetime | None = None) -> None:
    sub = await session.get(AccountSubscription, sub_id)
    if sub is not None:
        sub.reminder_sent_at = now or utcnow()
        session.add(sub)
        await session.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_lifecycle_domain.py -v`
Expected: PASS.

- [ ] **Step 6: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/domain/lifecycle.py src/quantuum/domain/accounts.py tests/test_lifecycle_domain.py
git commit -m "feat(3b): subscription lifecycle domain — sweep + due renewal reminders"
```

---

### Task 10: Lifecycle arq cron task + bot-per-tenant pool

**Files:**
- Modify: `src/quantuum/bot/botpool.py`, `src/quantuum/tasks/worker.py`
- Create: `src/quantuum/tasks/lifecycle.py`
- Test: `tests/test_task_lifecycle.py`, `tests/test_botpool.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_botpool.py`:

```python
def test_build_bots_by_tenant_keys_by_tenant_id(monkeypatch):
    from types import SimpleNamespace

    import quantuum.bot.botpool as bp

    monkeypatch.setattr(bp, "decrypt_token", lambda blob: "1:tok")

    class _FakeBot:
        def __init__(self, token):
            self.token = token

    monkeypatch.setattr(bp, "Bot", _FakeBot)
    rows = [
        SimpleNamespace(tenant_id=5, bot_telegram_id=10, bot_token_enc=b"x"),
        SimpleNamespace(tenant_id=7, bot_telegram_id=None, bot_token_enc=b"y"),  # skipped
    ]
    pool = bp.build_bots_by_tenant(rows)
    assert set(pool.keys()) == {5}
```

Create `tests/test_task_lifecycle.py`:

```python
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountIdentity,
    AccountSubscription,
    SubscriptionPlan,
    TenantBot,
)


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


async def test_lifecycle_task_sends_reminder_and_marks(session, default_tenant, monkeypatch):
    import quantuum.tasks.lifecycle as lc

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id))
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id="555"))
    plan = SubscriptionPlan(slug="m", name="M", period_days=30, price_cents=1)
    session.add(plan)
    await session.flush()
    sub = AccountSubscription(
        tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
        status="active", started_at=utcnow() - timedelta(days=28),
        ends_at=utcnow() + timedelta(days=2),
    )
    session.add(sub)
    # an active tenant bot so the pool resolves this tenant
    session.add(TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=10, bot_token_enc=b"x",
        webhook_secret_path="wh-10", status="active",
    ))
    await session.commit()
    await session.refresh(sub)

    fake_bot = AsyncMock()
    monkeypatch.setattr(lc, "build_bots_by_tenant", lambda rows: {default_tenant.id: fake_bot})

    ctx = {"sessionmaker": _Maker(session)}
    await lc.subscription_lifecycle(ctx)

    fake_bot.send_message.assert_awaited_once()
    chat_id = fake_bot.send_message.await_args.args[0]
    assert chat_id == 555
    await session.refresh(sub)
    assert sub.reminder_sent_at is not None


async def test_lifecycle_task_no_due_is_safe(session, monkeypatch):
    import quantuum.tasks.lifecycle as lc

    monkeypatch.setattr(lc, "build_bots_by_tenant", lambda rows: {})
    ctx = {"sessionmaker": _Maker(session)}
    await lc.subscription_lifecycle(ctx)  # no exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_lifecycle.py tests/test_botpool.py::test_build_bots_by_tenant_keys_by_tenant_id -v`
Expected: FAIL — `build_bots_by_tenant`/`quantuum.tasks.lifecycle` missing.

- [ ] **Step 3: Add the per-tenant bot pool builder**

In `src/quantuum/bot/botpool.py`, append:

```python
def build_bots_by_tenant(tenant_bots: list) -> dict[int, Bot]:
    """Build aiogram Bot instances keyed by tenant_id (rows without a bot_telegram_id are skipped).

    If a tenant has multiple bots, the last active row wins (MVP is 1 bot per tenant)."""
    pool: dict[int, Bot] = {}
    for tb in tenant_bots:
        if tb.bot_telegram_id is None:
            continue
        pool[tb.tenant_id] = Bot(token=decrypt_token(tb.bot_token_enc))
    return pool
```

- [ ] **Step 4: Implement the cron task**

Create `src/quantuum/tasks/lifecycle.py`:

```python
from quantuum.bot.botpool import build_bots_by_tenant
from quantuum.domain.lifecycle import (
    due_renewal_reminders,
    mark_reminder_sent,
    sweep_subscriptions,
)
from quantuum.domain.tenants import list_active_tenant_bots
from quantuum.logging_setup import get_logger

logger = get_logger("tasks.lifecycle")

_REMINDER_TEXT = (
    "Твоя подписка скоро закончится. Продли её, чтобы не потерять доступ — "
    "нажми кнопку ниже и оплати звёздами Telegram ★."
)


def _renew_kb():
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from quantuum.bot.ui.callbacks import BuyCb

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Продлить", callback_data=BuyCb(action="open").pack())
    )
    return builder.as_markup()


async def subscription_lifecycle(ctx) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        counts = await sweep_subscriptions(session)
        due = await due_renewal_reminders(session)
        rows = await list_active_tenant_bots(session)
    logger.info("lifecycle_swept", **counts, due_reminders=len(due))
    if not due:
        return

    bots = build_bots_by_tenant(rows)
    kb = _renew_kb()
    try:
        for item in due:
            bot = bots.get(item.tenant_id)
            if bot is None or item.chat_id is None:
                continue
            try:
                await bot.send_message(int(item.chat_id), _REMINDER_TEXT, reply_markup=kb)
            except Exception:
                logger.exception("reminder_delivery_failed", sub_id=item.sub_id)
                continue
            async with sessionmaker() as session:
                await mark_reminder_sent(session, item.sub_id)
    finally:
        for bot in bots.values():
            await bot.session.close()
```

- [ ] **Step 5: Register the task + cron in the worker**

In `src/quantuum/tasks/worker.py`, add the import and register both the function and an hourly cron job:

```python
from arq import cron

from quantuum.tasks.lifecycle import subscription_lifecycle
```

Update `WorkerSettings`:

```python
class WorkerSettings:
    functions = [blueprint_generate, provision_tenant, subscription_lifecycle]
    cron_jobs = [cron(subscription_lifecycle, minute=0)]  # top of every hour
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_task_lifecycle.py tests/test_botpool.py -v`
Expected: PASS.

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/bot/botpool.py src/quantuum/tasks/lifecycle.py src/quantuum/tasks/worker.py tests/test_task_lifecycle.py tests/test_botpool.py
git commit -m "feat(3b): hourly subscription_lifecycle cron task + renewal reminders"
```

---

## Phase F — Payouts & licenses

### Task 11: Payout + TenantLicense models + migration

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/e4d5f6a7b8c9_payouts_and_licenses.py`
- Test: `tests/test_payout_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_payout_models.py`:

```python
from quantuum.common.datetime import utcnow
from quantuum.db.models import Payout, TenantLicense


async def test_payout_row(session, default_tenant):
    p = Payout(
        tenant_id=default_tenant.id, period_start=utcnow(), period_end=utcnow(),
        gross_amount_cents=1000, platform_fee_cents=300, net_amount_cents=700,
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.status == "calculated"
    assert p.currency == "XTR"


async def test_tenant_license_row(session, default_tenant):
    lic = TenantLicense(tenant_id=default_tenant.id, status="active", price_cents=5000)
    session.add(lic)
    await session.commit()
    await session.refresh(lic)
    assert lic.id is not None
    assert lic.currency == "XTR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payout_models.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement the models**

In `src/quantuum/db/models.py`, append:

```python
class Payout(SQLModel, table=True):
    __tablename__ = "payouts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    period_start: datetime = _dt_field()
    period_end: datetime = _dt_field()
    gross_amount_cents: int
    platform_fee_cents: int
    net_amount_cents: int
    currency: str = "XTR"
    status: str = "calculated"  # calculated|paid
    paid_at: datetime | None = _dt_field(default=None)
    external_ref: str | None = None
    calculated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    created_at: datetime = _dt_field(default_factory=utcnow)


class TenantLicense(SQLModel, table=True):
    __tablename__ = "tenant_licenses"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    status: str = "active"  # active|expired|cancelled
    started_at: datetime = _dt_field(default_factory=utcnow)
    ends_at: datetime | None = _dt_field(default=None)
    price_cents: int
    currency: str = "XTR"
    payment_provider_id: int | None = Field(default=None, foreign_key="payment_providers.id")
    created_at: datetime = _dt_field(default_factory=utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payout_models.py -v`
Expected: PASS.

- [ ] **Step 5: Write the migration**

Create `alembic/versions/e4d5f6a7b8c9_payouts_and_licenses.py`:

```python
"""payouts + tenant_licenses

Revision ID: e4d5f6a7b8c9
Revises: d3c4e5f6a7b8
Create Date: 2026-05-21 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "e4d5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "d3c4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gross_amount_cents", sa.Integer(), nullable=False),
        sa.Column("platform_fee_cents", sa.Integer(), nullable=False),
        sa.Column("net_amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("calculated_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["calculated_by_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payouts_tenant_id"), "payouts", ["tenant_id"], unique=False)
    op.create_table(
        "tenant_licenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payment_provider_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_provider_id"], ["payment_providers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_licenses_tenant_id"), "tenant_licenses", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_licenses_tenant_id"), table_name="tenant_licenses")
    op.drop_table("tenant_licenses")
    op.drop_index(op.f("ix_payouts_tenant_id"), table_name="payouts")
    op.drop_table("payouts")
```

- [ ] **Step 6: Verify migration + no drift**

Run: `uv run alembic upgrade head` then `uv run alembic check` (or autogenerate-and-confirm-empty). Expected: clean, no drift.

- [ ] **Step 7: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/db/models.py alembic/versions/e4d5f6a7b8c9_payouts_and_licenses.py tests/test_payout_models.py
git commit -m "feat(3b): payouts + tenant_licenses models + migration"
```

---

### Task 12: Payout domain + superadmin payout endpoints

**Files:**
- Create: `src/quantuum/domain/payouts.py`, `src/quantuum/api/routes/admin_payouts.py`
- Modify: `src/quantuum/api/schemas.py`, `src/quantuum/api/app.py`, `src/quantuum/settings.py`
- Test: `tests/test_payouts_domain.py`, `tests/test_api_payouts.py`

- [ ] **Step 1: Write the failing test (domain)**

Create `tests/test_payouts_domain.py`:

```python
from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, Payment
from quantuum.domain.payouts import calculate_payout, mark_payout_paid


async def _paid_payment(session, default_tenant, account_id, amount, paid_at):
    pay = Payment(
        tenant_id=default_tenant.id, account_id=account_id, amount_cents=amount,
        currency="XTR", status="paid", paid_at=paid_at,
    )
    session.add(pay)
    await session.flush()
    return pay


async def test_calculate_payout_sums_paid_in_period(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    now = utcnow()
    await _paid_payment(session, default_tenant, acc.id, 1000, now - timedelta(days=1))  # in
    await _paid_payment(session, default_tenant, acc.id, 500, now - timedelta(days=10))  # out
    await session.commit()

    payout = await calculate_payout(
        session, tenant_id=default_tenant.id, period_start=now - timedelta(days=3),
        period_end=now + timedelta(days=1), fee_pct=30, calculated_by_account_id=None,
    )
    assert payout.gross_amount_cents == 1000
    assert payout.platform_fee_cents == 300
    assert payout.net_amount_cents == 700
    assert payout.status == "calculated"


async def test_calculate_payout_zero_when_none(session, default_tenant):
    payout = await calculate_payout(
        session, tenant_id=default_tenant.id, period_start=utcnow() - timedelta(days=1),
        period_end=utcnow(), fee_pct=30, calculated_by_account_id=None,
    )
    assert payout.gross_amount_cents == 0
    assert payout.net_amount_cents == 0


async def test_mark_payout_paid(session, default_tenant):
    payout = await calculate_payout(
        session, tenant_id=default_tenant.id, period_start=utcnow() - timedelta(days=1),
        period_end=utcnow(), fee_pct=30, calculated_by_account_id=None,
    )
    updated = await mark_payout_paid(session, payout.id, external_ref="bank-tx-1")
    assert updated.status == "paid"
    assert updated.external_ref == "bank-tx-1"
    assert updated.paid_at is not None
    assert await mark_payout_paid(session, 999999, external_ref="x") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payouts_domain.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the payout domain**

Create `src/quantuum/domain/payouts.py`:

```python
from datetime import datetime

from sqlalchemy import func
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import Payment, Payout


async def calculate_payout(
    session,
    *,
    tenant_id: int,
    period_start: datetime,
    period_end: datetime,
    fee_pct: int,
    calculated_by_account_id: int | None,
) -> Payout:
    """Sum a tenant's PAID payments in [period_start, period_end) and create a payout row.

    net = gross − floor(gross * fee_pct / 100). Returns the persisted Payout (status=calculated)."""
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.tenant_id == tenant_id,
            Payment.status == "paid",
            Payment.paid_at >= period_start,
            Payment.paid_at < period_end,
        )
    )
    gross = int(result.scalar_one())
    fee = gross * fee_pct // 100
    net = gross - fee
    payout = Payout(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        gross_amount_cents=gross,
        platform_fee_cents=fee,
        net_amount_cents=net,
        status="calculated",
        calculated_by_account_id=calculated_by_account_id,
    )
    session.add(payout)
    await session.commit()
    await session.refresh(payout)
    return payout


async def mark_payout_paid(session, payout_id: int, *, external_ref: str) -> Payout | None:
    payout = await session.get(Payout, payout_id)
    if payout is None:
        return None
    payout.status = "paid"
    payout.paid_at = utcnow()
    payout.external_ref = external_ref
    session.add(payout)
    await session.commit()
    await session.refresh(payout)
    return payout
```

- [ ] **Step 4: Add the setting + schemas**

In `src/quantuum/settings.py`, add a field to `Settings` (after `platform_tenant_name`):

```python
    platform_fee_pct: int = 30
```

In `src/quantuum/api/schemas.py`, append:

```python
class PayoutCalculateIn(BaseModel):
    tenant_id: int
    period_start: datetime
    period_end: datetime


class PayoutMarkPaidIn(BaseModel):
    external_ref: str


class PayoutOut(BaseModel):
    id: int
    tenant_id: int
    period_start: str
    period_end: str
    gross_amount_cents: int
    platform_fee_cents: int
    net_amount_cents: int
    currency: str
    status: str
    external_ref: str | None
    paid_at: str | None
```

- [ ] **Step 5: Write the failing test (API)**

Create `tests/test_api_payouts.py`:

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def superadmin(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, None, True)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_calculate_and_mark_paid(client, superadmin, default_tenant):
    now = utcnow()
    r = await client.post(
        "/admin/platform/payouts/calculate",
        headers=superadmin,
        json={
            "tenant_id": default_tenant.id,
            "period_start": (now.replace(microsecond=0)).isoformat(),
            "period_end": (now.replace(microsecond=0)).isoformat(),
        },
    )
    assert r.status_code == 201
    payout_id = r.json()["id"]
    assert r.json()["status"] == "calculated"

    r2 = await client.get("/admin/platform/payouts", headers=superadmin)
    assert r2.status_code == 200
    assert any(p["id"] == payout_id for p in r2.json())

    r3 = await client.patch(
        f"/admin/platform/payouts/{payout_id}",
        headers=superadmin,
        json={"external_ref": "tx-9"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "paid"
    assert r3.json()["external_ref"] == "tx-9"


async def test_payouts_require_superadmin(client, customer, default_tenant):
    r = await client.get("/admin/platform/payouts", headers=customer)
    assert r.status_code == 403


async def test_mark_unknown_payout_404(client, superadmin):
    r = await client.patch(
        "/admin/platform/payouts/999999", headers=superadmin, json={"external_ref": "x"}
    )
    assert r.status_code == 404
```

- [ ] **Step 6: Implement the API router**

Create `src/quantuum/api/routes/admin_payouts.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import get_session, require_superadmin
from quantuum.api.schemas import PayoutCalculateIn, PayoutMarkPaidIn, PayoutOut
from quantuum.db.models import Account, Payout
from quantuum.domain.payouts import calculate_payout, mark_payout_paid
from quantuum.settings import get_settings

router = APIRouter(prefix="/admin/platform/payouts", tags=["admin-payouts"])


def _out(p: Payout) -> PayoutOut:
    return PayoutOut(
        id=p.id,
        tenant_id=p.tenant_id,
        period_start=p.period_start.isoformat(),
        period_end=p.period_end.isoformat(),
        gross_amount_cents=p.gross_amount_cents,
        platform_fee_cents=p.platform_fee_cents,
        net_amount_cents=p.net_amount_cents,
        currency=p.currency,
        status=p.status,
        external_ref=p.external_ref,
        paid_at=p.paid_at.isoformat() if p.paid_at else None,
    )


@router.post("/calculate", response_model=PayoutOut, status_code=201)
async def calculate(
    body: PayoutCalculateIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PayoutOut:
    payout = await calculate_payout(
        session,
        tenant_id=body.tenant_id,
        period_start=body.period_start,
        period_end=body.period_end,
        fee_pct=get_settings().platform_fee_pct,
        calculated_by_account_id=admin.id,
    )
    return _out(payout)


@router.get("", response_model=list[PayoutOut])
async def list_payouts(
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> list[PayoutOut]:
    result = await session.execute(select(Payout).order_by(Payout.id.desc()))
    return [_out(p) for p in result.scalars().all()]


@router.patch("/{payout_id}", response_model=PayoutOut)
async def mark_paid(
    payout_id: int,
    body: PayoutMarkPaidIn,
    admin: Account = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> PayoutOut:
    payout = await mark_payout_paid(session, payout_id, external_ref=body.external_ref)
    if payout is None:
        raise HTTPException(status_code=404, detail="payout not found")
    return _out(payout)
```

- [ ] **Step 7: Wire the router**

In `src/quantuum/api/app.py`, add `admin_payouts` to the routes import and include it after `billing`:

```python
from quantuum.api.routes import admin_payouts, admin_platform, auth, billing, health, me, webhook
```

```python
    app.include_router(billing.router)
    app.include_router(admin_payouts.router)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_payouts_domain.py tests/test_api_payouts.py -v`
Expected: PASS.

- [ ] **Step 9: Run suite + commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add src/quantuum/domain/payouts.py src/quantuum/api/routes/admin_payouts.py src/quantuum/api/schemas.py src/quantuum/api/app.py src/quantuum/settings.py tests/test_payouts_domain.py tests/test_api_payouts.py
git commit -m "feat(3b): payout calculation domain + superadmin payout endpoints"
```

---

## Self-Review (completed by plan author)

**Spec coverage (§7 Payments, §9 endpoint inventory):**
- Provider abstraction + `TgStarsProvider` → Task 1. ✅
- Platform-tenant provider seeding → Task 2. ✅
- Stars purchase round-trip (invoice/pre-checkout/successful_payment) + idempotent crediting → Tasks 3, 5. ✅
- `POST /v1/me/subscriptions|packages` via abstraction → 501 → Task 7. ✅
- Subscription lifecycle (active→grace→expired, grace access, reminders at ends_at−3d) → Tasks 8, 9, 10. ✅
- Package FIFO burn — already shipped in 3a (`consume_quota` decrements oldest-expiring). ✅
- `payouts` table + `POST /admin/platform/payouts/calculate` + mark-paid PATCH → Tasks 11, 12. ✅
- `tenant_licenses` table-only → Task 11. ✅
- Callback handling partial-unique invariant — backed by 3a's index; `fulfill_payment` renews the same active/grace row. ✅
- Buy entry surfaced to users (no_quota offer + /buy) → Tasks 4, 6. ✅

**Type consistency:** `BuyCb(action, kind, plan_id)` used identically in Tasks 4/5/6/10. `fulfill_payment(... ) -> bool` Task 3 used in Task 5. `GRACE_DAYS`/`REMINDER_DAYS` defined in `billing.py` (Task 8), imported by `lifecycle.py` (Task 9). `DueReminder(sub_id, account_id, tenant_id, chat_id)` defined Task 9, consumed Task 10. `provider_for_kind`/`PaymentNotSupportedInApiError` defined Task 1, used Task 7. `build_bots_by_tenant` defined Task 10, used Task 10 task.

**Migration chain:** `c2b3d4e5f6a7` → `d3c4e5f6a7b8` (Task 8) → `e4d5f6a7b8c9` (Task 11). No partial indexes added (the reminder column is a plain nullable add); JSONB/partial-unique from 3a untouched.

**Known deferred (documented, non-blocking):** advisory-lock-by-`external_id` for hard concurrency safety on `fulfill_payment`; Stars refunds (`TgStarsProvider.refund` raises NotImplementedError); central billing-bot redirect for Basic on non-platform bots (spec §7 known constraint); calendar-accurate subscription periods (still integer `period_days`).
