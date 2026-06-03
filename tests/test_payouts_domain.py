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


async def test_calculate_payout_is_idempotent(session, default_tenant):
    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from quantuum.db.models import Payout

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
