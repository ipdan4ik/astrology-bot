from quantuum.db.models import Account, AccountBalance
from quantuum.domain.accounts import (
    adjust_package_credits,
    clear_account_ban,
    is_tenant_staff,
    set_account_ban,
)
from quantuum.domain.tenants import grant_role


async def _make_account(session, tenant_id):
    acc = Account(tenant_id=tenant_id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_adjust_creates_balance_and_adds(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    new_balance = await adjust_package_credits(session, acc.id, 5)
    await session.commit()
    assert new_balance == 5
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5


async def test_adjust_deducts_and_clamps_at_zero(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await adjust_package_credits(session, acc.id, 3)
    clamped = await adjust_package_credits(session, acc.id, -10)
    await session.commit()
    assert clamped == 0


async def test_set_and_clear_ban(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await set_account_ban(session, acc.id, reason="abuse")
    await session.commit()
    await session.refresh(acc)
    assert acc.status == "disabled" and acc.ban_reason == "abuse"

    await clear_account_ban(session, acc.id)
    await session.commit()
    await session.refresh(acc)
    assert acc.status == "active" and acc.ban_reason is None


async def test_is_tenant_staff(session, default_tenant):
    owner = await _make_account(session, default_tenant.id)
    customer = await _make_account(session, default_tenant.id)
    await grant_role(session, tenant_id=default_tenant.id, account_id=owner.id, role="owner")
    await session.commit()
    assert await is_tenant_staff(session, tenant_id=default_tenant.id, account_id=owner.id) is True
    assert await is_tenant_staff(session, tenant_id=default_tenant.id, account_id=customer.id) is False
