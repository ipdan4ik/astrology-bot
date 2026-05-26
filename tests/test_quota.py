import pytest

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.domain.quota import consume_quota, refund_quota


async def _make_account(session, tenant_id):
    from quantuum.auth.identity import find_or_create_account_by_tg

    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="1")


async def test_new_account_receives_signup_credits(session, default_tenant):
    from quantuum.auth.identity import SIGNUP_CREDITS
    from quantuum.db.models import AccountBalance

    acc = await _make_account(session, default_tenant.id)
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == SIGNUP_CREDITS
    assert bal.free_trial_used is True


async def test_first_blueprint_uses_signup_credits(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "package"


async def test_blocked_after_signup_credits_exhausted(session, default_tenant):
    from quantuum.auth.identity import SIGNUP_CREDITS

    acc = await _make_account(session, default_tenant.id)
    for _ in range(SIGNUP_CREDITS):
        await consume_quota(session, acc.id, "blueprint")
    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint")


async def test_refund_package_restores_signup_credit(session, default_tenant):
    from quantuum.db.models import AccountBalance, Request

    acc = await _make_account(session, default_tenant.id)
    bal_before = await session.get(AccountBalance, acc.id)
    starting = bal_before.package_credits
    await consume_quota(session, acc.id, "blueprint")
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against="package", cost_units=1,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)
    bal_after = await session.get(AccountBalance, acc.id)
    await session.refresh(bal_after)
    assert bal_after.package_credits == starting


async def test_consume_decrements_oldest_package_row(session, default_tenant):
    from datetime import timedelta

    from quantuum.common.datetime import utcnow
    from quantuum.db.models import Account, AccountBalance, AccountPackage, PackagePlan
    from quantuum.domain.quota import consume_quota

    acc = Account(tenant_id=default_tenant.id)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=1)
    session.add(acc)
    session.add(plan)
    await session.flush()
    # mark trial used so consume falls through to packages
    session.add(AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=2))
    older = AccountPackage(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                           requests_remaining=1, expires_at=utcnow() + timedelta(days=1))
    newer = AccountPackage(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                           requests_remaining=1, expires_at=utcnow() + timedelta(days=30))
    session.add(older)
    session.add(newer)
    await session.commit()

    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "package"

    await session.refresh(older)
    await session.refresh(newer)
    assert older.requests_remaining == 0  # oldest-expiring decremented first
    assert newer.requests_remaining == 1
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 1


async def test_refund_package_restores_credit(session, default_tenant):
    from datetime import timedelta

    from quantuum.common.datetime import utcnow
    from quantuum.db.models import Account, AccountBalance, AccountPackage, PackagePlan, Request
    from quantuum.domain.quota import refund_quota

    acc = Account(tenant_id=default_tenant.id)
    plan = PackagePlan(slug="s", name="S", request_count=5, price_cents=1)
    session.add(acc)
    session.add(plan)
    await session.flush()
    session.add(AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=0))
    session.add(AccountPackage(tenant_id=default_tenant.id, account_id=acc.id, plan_id=plan.id,
                               requests_remaining=0, expires_at=utcnow() + timedelta(days=30)))
    req = Request(tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
                  status="failed", charged_against="package")
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 1
