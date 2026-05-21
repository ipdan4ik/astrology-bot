from datetime import date, time
from decimal import Decimal

import pytest

from quantuum.common.exceptions import NotFoundError
from quantuum.domain.transits import (
    create_transit,
    get_transit,
    list_transits,
    resolve_natal,
    set_transit_status,
)


async def _account_and_profile(session, tenant_id, *, tg_user_id="9"):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg_user_id)
    profile = NatalProfile(
        tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


async def test_create_get_roundtrip(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    row = await create_transit(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, window_days=None, lang="ru",
    )
    assert row.status == "pending"
    assert row.window_days == 90  # None -> default
    reloaded = await get_transit(session, row.id)
    assert reloaded.id == row.id and reloaded.lang == "ru"


async def test_create_clamps_window(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    row = await create_transit(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, window_days=9999, lang="ru",
    )
    assert row.window_days == 180  # clamped to MAX


async def test_get_missing_raises(session, default_tenant):
    with pytest.raises(NotFoundError):
        await get_transit(session, 999999)


async def test_list_newest_first(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    r1 = await create_transit(session, tenant_id=default_tenant.id, account_id=acc.id,
                              natal_profile_id=profile.id, window_days=30, lang="ru")
    r2 = await create_transit(session, tenant_id=default_tenant.id, account_id=acc.id,
                              natal_profile_id=profile.id, window_days=30, lang="ru")
    rows = await list_transits(session, account_id=acc.id)
    assert [r.id for r in rows] == [r2.id, r1.id]


async def test_set_status_done_sets_completed(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    row = await create_transit(session, tenant_id=default_tenant.id, account_id=acc.id,
                               natal_profile_id=profile.id, window_days=30, lang="ru")
    await set_transit_status(session, row.id, "done", report_md="R", llm_tokens_in=7)
    reloaded = await get_transit(session, row.id)
    assert reloaded.status == "done"
    assert reloaded.report_md == "R"
    assert reloaded.llm_tokens_in == 7
    assert reloaded.completed_at is not None


async def test_resolve_natal_uses_existing_blueprint(session, default_tenant):
    from quantuum.db.models import Blueprint

    acc, profile = await _account_and_profile(session, default_tenant.id)
    bp = Blueprint(
        tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
        status="done", calc_md="# Quantuum Blueprint — existing",
    )
    session.add(bp)
    await session.commit()
    await session.refresh(bp)

    inp, natal_md, blueprint_id = await resolve_natal(
        session, account_id=acc.id, natal_profile_id=profile.id
    )
    assert natal_md == "# Quantuum Blueprint — existing"
    assert blueprint_id == bp.id
    assert inp.full_name == "Anna"


async def test_resolve_natal_builds_when_no_blueprint(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    inp, natal_md, blueprint_id = await resolve_natal(
        session, account_id=acc.id, natal_profile_id=profile.id
    )
    assert blueprint_id is None
    assert natal_md.startswith("# Quantuum Blueprint —")


async def test_resolve_natal_missing_profile_raises(session, default_tenant):
    with pytest.raises(NotFoundError):
        await resolve_natal(session, account_id=1, natal_profile_id=999999)
