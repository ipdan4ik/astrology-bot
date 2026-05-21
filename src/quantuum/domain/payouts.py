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

    net = gross - floor(gross * fee_pct / 100). Returns the persisted Payout (status=calculated)."""
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
