from quantuum.db.models import Account
from quantuum.domain.billing import (
    get_payment_by_external_id,
    mark_payment_paid,
    record_pending_payment,
)


async def _account(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    return acc


async def test_record_pending_payment(session, default_tenant):
    acc = await _account(session, default_tenant)
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR", metadata={"kind": "subscription", "plan_id": 1},
    )
    assert pay.id is not None
    assert pay.status == "pending"
    assert pay.metadata_json["plan_id"] == 1


async def test_mark_payment_paid_idempotent(session, default_tenant):
    acc = await _account(session, default_tenant)
    pay = await record_pending_payment(
        session, tenant_id=default_tenant.id, account_id=acc.id, provider_id=None,
        amount_cents=250, currency="XTR", metadata={},
    )
    p1 = await mark_payment_paid(session, payment_id=pay.id, external_id="charge_123")
    assert p1.status == "paid"
    assert p1.external_id == "charge_123"
    assert p1.paid_at is not None
    first_paid_at = p1.paid_at

    # Idempotent: marking again does not change paid_at or duplicate
    p2 = await mark_payment_paid(session, payment_id=pay.id, external_id="charge_123")
    assert p2.paid_at == first_paid_at

    found = await get_payment_by_external_id(session, "charge_123")
    assert found is not None and found.id == pay.id
