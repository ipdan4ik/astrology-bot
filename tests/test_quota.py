import pytest

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.domain.quota import consume_quota, refund_quota


async def _make_account(session, tenant_id):
    from quantuum.auth.identity import find_or_create_account_by_tg

    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="1")


async def test_first_blueprint_uses_trial(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"


async def test_second_blueprint_blocked(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint")


async def test_refund_restores_trial(session, default_tenant):
    from quantuum.db.models import Request

    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint", charged_against="trial"
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)

    # trial available again
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"


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
