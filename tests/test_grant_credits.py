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
