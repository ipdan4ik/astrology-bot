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
