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
