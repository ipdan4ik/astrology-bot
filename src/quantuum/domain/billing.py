from datetime import timedelta

from sqlmodel import or_, select

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AccountPackage,
    AccountSubscription,
    PackagePlan,
    Payment,
    SubscriptionPlan,
)
from quantuum.domain.plans import get_package_plan, get_subscription_plan

GRACE_DAYS = 5  # spec §7: grace window grants this many days of access past ends_at
REMINDER_DAYS = 3  # spec §7: renewal reminder fires this many days before ends_at


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


async def _ensure_balance(session, account_id: int) -> AccountBalance:
    balance = await session.get(AccountBalance, account_id)
    if balance is None:
        balance = AccountBalance(account_id=account_id)
        session.add(balance)
        await session.flush()
    return balance


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
    balance.package_credits = balance.package_credits + amount
    balance.updated_at = now
    session.add(balance)
    await session.flush()
    return pkg


async def recompute_account_balance(session, account_id: int) -> AccountBalance:
    """Recompute package_credits (sum of valid package rows) and subscription_active_until
    (latest active/grace subscription end) from the ledger tables."""
    now = utcnow()
    balance = await _ensure_balance(session, account_id)

    balance.package_credits = await _sum_valid_packages(session, account_id)

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
            AccountSubscription.tenant_id == tenant_id,
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
        sub.reminder_sent_at = None
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
    pkg = await grant_credits(
        session,
        account_id=account_id,
        tenant_id=tenant_id,
        amount=plan.request_count,
        source="purchase",
        expires_at=expires_at,
        payment_id=payment_id,
        plan_id=plan.id,
    )
    await session.commit()
    await session.refresh(pkg)
    return pkg


async def fulfill_payment(session, *, payment_id: int, external_id: str) -> bool:
    """Idempotently mark a payment paid and apply its crediting.

    Returns True if this call performed the fulfillment (the pending->paid transition);
    False if the payment is unknown or was already paid. Crediting happens ONLY on the
    transition, so duplicate/redelivered payment events never double-credit.
    """
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.status != "pending":
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
    if kind == "subscription" and plan_id is not None:
        plan = await get_subscription_plan(session, plan_id, tenant_id=payment.tenant_id)
        if plan is not None:
            await apply_subscription_payment(
                session, account_id=payment.account_id, tenant_id=payment.tenant_id,
                plan=plan, payment_id=payment.id,
            )
    elif kind == "package" and plan_id is not None:
        plan = await get_package_plan(session, plan_id, tenant_id=payment.tenant_id)
        if plan is not None:
            await apply_package_payment(
                session, account_id=payment.account_id, tenant_id=payment.tenant_id,
                plan=plan, payment_id=payment.id,
            )
    return True
