from quantuum.db.models import AccountBalance, AccountPackage
from quantuum.domain.billing import (
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


async def test_granted_credits_survive_recompute(session, default_tenant):
    """Regression for the source-of-truth bug: ledger-backed credits must not be
    wiped when recompute_account_balance rebuilds the counter from the ledger."""
    from quantuum.db.models import Account, AccountBalance

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id, package_credits=0))
    await session.flush()

    await grant_credits(
        session, account_id=acc.id, tenant_id=default_tenant.id, amount=5, source="gift"
    )
    await session.commit()

    await recompute_account_balance(session, acc.id)
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5  # ledger-backed gift survives recompute


async def test_grant_credits_rejects_non_positive(session, default_tenant):
    import pytest

    acc = await _account(session, default_tenant)
    with pytest.raises(ValueError):
        await grant_credits(
            session, account_id=acc.id, tenant_id=default_tenant.id, amount=0, source="gift"
        )


async def test_manual_grant_is_ledger_backed_and_deduct_drains(session, default_tenant):
    from sqlmodel import select

    from quantuum.db.models import AccountBalance, AccountPackage
    from quantuum.domain.accounts import adjust_package_credits

    acc = await _account(session, default_tenant)
    start = (await session.get(AccountBalance, acc.id)).package_credits

    after_grant = await adjust_package_credits(session, acc.id, 5)
    await session.commit()
    assert after_grant == start + 5
    rows = (
        await session.execute(
            select(AccountPackage).where(
                AccountPackage.account_id == acc.id, AccountPackage.source == "manual"
            )
        )
    ).scalars().all()
    assert any(r.requests_remaining == 5 for r in rows)

    after_deduct = await adjust_package_credits(session, acc.id, -3)
    await session.commit()
    assert after_deduct == after_grant - 3
    from quantuum.domain.billing import _sum_valid_packages
    assert after_deduct == await _sum_valid_packages(session, acc.id)
