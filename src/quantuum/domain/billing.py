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
