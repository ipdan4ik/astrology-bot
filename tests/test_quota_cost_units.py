import pytest

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, AccountPackage, PackagePlan, Request
from quantuum.domain.quota import consume_quota, refund_quota


async def _make_account(session, tenant_id):
    from quantuum.auth.identity import find_or_create_account_by_tg
    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="9999")


async def _make_plan(session):
    plan = PackagePlan(slug="test-plan", name="Test Plan", request_count=10, price_cents=100)
    session.add(plan)
    await session.flush()
    return plan


async def _setup_package_balance(session, acc, tenant_id, credits: int, requests_remaining: int):
    """Mark trial used and set package credits; update the auto-created balance row."""
    bal = await session.get(AccountBalance, acc.id)
    bal.free_trial_used = True
    bal.package_credits = credits
    session.add(bal)
    plan = await _make_plan(session)
    pkg = AccountPackage(
        tenant_id=tenant_id,
        account_id=acc.id,
        plan_id=plan.id,
        requests_remaining=requests_remaining,
    )
    session.add(pkg)
    await session.commit()
    return bal, pkg


async def test_consume_quota_deducts_cost_units(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    bal, pkg = await _setup_package_balance(session, acc, default_tenant.id, credits=5, requests_remaining=5)

    charged = await consume_quota(session, acc.id, "blueprint", cost_units=4)
    assert charged == "package"
    await session.refresh(bal)
    await session.refresh(pkg)
    assert bal.package_credits == 1
    assert pkg.requests_remaining == 1


async def test_consume_quota_rejects_when_balance_too_low(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    bal, pkg = await _setup_package_balance(session, acc, default_tenant.id, credits=3, requests_remaining=3)

    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint", cost_units=4)
    await session.refresh(bal)
    assert bal.package_credits == 3  # untouched


async def test_refund_quota_returns_cost_units(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    bal, pkg = await _setup_package_balance(session, acc, default_tenant.id, credits=5, requests_remaining=5)

    await consume_quota(session, acc.id, "blueprint", cost_units=4)
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against="package", cost_units=4,
    )
    session.add(req); await session.commit(); await session.refresh(req)

    await refund_quota(session, req.id)
    await session.refresh(bal); await session.refresh(pkg)
    assert bal.package_credits == 5
    assert pkg.requests_remaining == 5


async def test_trial_is_single_shot_regardless_of_cost_units(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint", cost_units=4)
    assert charged == "trial"
    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint", cost_units=1)
