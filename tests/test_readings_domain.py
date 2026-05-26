import pytest

from quantuum.common.exceptions import NotFoundError
from quantuum.domain.readings import (
    create_reading,
    get_reading,
    list_readings,
    set_reading_status,
)


async def _profile(session, default_tenant):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="d1")
    p = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id,
        full_name="X", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(p); await session.commit(); await session.refresh(p)
    return acc, p


async def test_create_reading_sets_pending(session, default_tenant):
    acc, prof = await _profile(session, default_tenant)
    r = await create_reading(session,
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, kind="bazi", lang="ru")
    assert r.status == "pending"
    assert r.kind == "bazi"


async def test_set_reading_status_terminal_sets_completed_at(session, default_tenant):
    acc, prof = await _profile(session, default_tenant)
    r = await create_reading(session,
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, kind="bazi", lang="ru")
    await set_reading_status(session, r.id, "done", llm_md="hello")
    r2 = await get_reading(session, r.id)
    assert r2.status == "done"
    assert r2.llm_md == "hello"
    assert r2.completed_at is not None


async def test_get_reading_not_found_raises(session):
    with pytest.raises(NotFoundError):
        await get_reading(session, 999999)


async def test_list_readings_filters_by_account(session, default_tenant):
    acc, prof = await _profile(session, default_tenant)
    await create_reading(session, tenant_id=default_tenant.id, account_id=acc.id,
                         natal_profile_id=prof.id, kind="bazi", lang="ru")
    await create_reading(session, tenant_id=default_tenant.id, account_id=acc.id,
                         natal_profile_id=prof.id, kind="numerology", lang="ru")
    rows = await list_readings(session, account_id=acc.id)
    assert {r.kind for r in rows} == {"bazi", "numerology"}
