import pytest


async def _profile(session, default_tenant, tg="alw1"):
    from datetime import date, time

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id=tg
    )
    p = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id,
        full_name="X", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return acc, p


async def test_set_reading_status_rejects_unknown_field(session, default_tenant):
    from quantuum.domain.readings import create_reading, set_reading_status

    acc, prof = await _profile(session, default_tenant, tg="alw_r1")
    reading = await create_reading(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, kind="bazi", lang="en",
    )
    # tenant_id is a REAL column but NOT a content field — must be rejected by the
    # allowlist (a plain setattr would silently succeed without it).
    with pytest.raises(ValueError):
        await set_reading_status(session, reading.id, "done", tenant_id=999)


async def test_set_reading_status_allows_known_field(session, default_tenant):
    from quantuum.domain.readings import create_reading, get_reading, set_reading_status

    acc, prof = await _profile(session, default_tenant, tg="alw_r2")
    reading = await create_reading(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, kind="bazi", lang="en",
    )
    await set_reading_status(session, reading.id, "done", llm_md="result")
    r = await get_reading(session, reading.id)
    assert r.llm_md == "result" and r.status == "done"


async def test_set_qa_status_rejects_unknown_field(session, default_tenant):
    from quantuum.db.models import QaAnswer
    from quantuum.domain.qa import set_qa_status

    acc, prof = await _profile(session, default_tenant, tg="alw_q1")
    qa = QaAnswer(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, question="q?", status="pending",
    )
    session.add(qa)
    await session.commit()
    await session.refresh(qa)
    with pytest.raises(ValueError):
        await set_qa_status(session, qa.id, "done", tenant_id=999)


async def test_set_transit_status_rejects_unknown_field(session, default_tenant):
    from quantuum.db.models import TransitReport
    from quantuum.domain.transits import set_transit_status

    acc, prof = await _profile(session, default_tenant, tg="alw_t1")
    row = TransitReport(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, status="pending",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    with pytest.raises(ValueError):
        await set_transit_status(session, row.id, "done", tenant_id=999)


async def test_set_horoscope_status_rejects_unknown_field(session, default_tenant):
    from datetime import date

    from quantuum.db.models import DailyHoroscope
    from quantuum.domain.daily import set_horoscope_status

    acc, prof = await _profile(session, default_tenant, tg="alw_h1")
    row = DailyHoroscope(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, local_date=date(2026, 6, 3), status="generating",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    with pytest.raises(ValueError):
        await set_horoscope_status(session, row.id, "done", tenant_id=999)
