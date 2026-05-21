from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import NatalProfile, TransitReport


async def _acc_profile(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="7")
    profile = NatalProfile(
        tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
        birth_date=date(1990, 6, 15), birth_time=time(14, 30), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6176"), timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


async def test_transit_report_defaults(session, default_tenant):
    acc, profile = await _acc_profile(session, default_tenant.id)
    row = TransitReport(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, window_days=90, lang="ru",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None
    assert row.status == "pending"
    assert row.window_days == 90
    assert row.as_of is None
    assert row.transit_md is None
    assert row.report_md is None
    assert row.created_at is not None
    assert row.completed_at is None
