from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import DailyHoroscope, DailySubscription, NatalProfile


async def _acc_profile(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="11")
    profile = NatalProfile(
        tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
        birth_date=date(1990, 6, 15), birth_time=time(14, 30), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6176"), timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


async def test_daily_subscription_defaults(session, default_tenant):
    acc, _ = await _acc_profile(session, default_tenant.id)
    row = DailySubscription(account_id=acc.id, tenant_id=default_tenant.id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.enabled is False
    assert row.send_hour == 9
    assert row.last_sent_on is None
    assert row.created_at is not None


async def test_daily_horoscope_unique_per_day(session, default_tenant):
    acc, profile = await _acc_profile(session, default_tenant.id)
    a = DailyHoroscope(
        tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
        local_date=date(2026, 3, 1), lang="ru",
    )
    session.add(a)
    await session.commit()
    assert a.status == "generating"

    b = DailyHoroscope(
        tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
        local_date=date(2026, 3, 1), lang="ru",
    )
    session.add(b)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
