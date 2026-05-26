from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import Account, AccountBalance
from quantuum.domain.accounts import (
    adjust_package_credits,
    clear_account_ban,
    count_tenant_customers,
    get_customer_card,
    is_tenant_staff,
    list_tenant_customers,
    set_account_ban,
)
from quantuum.domain.natal_profiles import upsert_natal_profile
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


async def test_list_and_count_with_pagination(session, default_tenant):
    from quantuum.auth.identity import SIGNUP_CREDITS

    for i in range(3):
        await find_or_create_account_by_tg(
            session, tenant_id=default_tenant.id, tg_user_id=str(1000 + i)
        )
    assert await count_tenant_customers(session, default_tenant.id) == 3

    page = await list_tenant_customers(session, default_tenant.id, limit=2, offset=0)
    assert len(page) == 2
    assert page[0].tg_user_id == "1000"
    assert page[0].package_credits == SIGNUP_CREDITS
    assert page[0].full_name is None

    page2 = await list_tenant_customers(session, default_tenant.id, limit=2, offset=2)
    assert len(page2) == 1


async def test_card_maps_name_credits_and_ban(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="2000"
    )
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    from quantuum.auth.identity import SIGNUP_CREDITS

    await adjust_package_credits(session, acc.id, 7)
    await set_account_ban(session, acc.id, reason="spam")
    await session.commit()

    card = await get_customer_card(session, default_tenant.id, acc.id)
    assert card.full_name == "Anna"
    assert card.tg_user_id == "2000"
    assert card.package_credits == SIGNUP_CREDITS + 7
    assert card.status == "disabled"
    assert card.ban_reason == "spam"


async def test_card_none_for_wrong_tenant(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="2001"
    )
    await session.commit()
    assert await get_customer_card(session, 999999, acc.id) is None
