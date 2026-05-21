import pytest

from quantuum.common.exceptions import NotFoundError
from quantuum.domain.qa import (
    create_qa,
    get_qa,
    list_qa,
    resolve_calc_md,
    set_qa_status,
)


async def _account_and_profile(session, tenant_id, *, tg_user_id="9"):
    from datetime import date, time
    from decimal import Decimal

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg_user_id
    )
    profile = NatalProfile(
        tenant_id=tenant_id,
        account_id=acc.id,
        full_name="Anna",
        birth_date=date(1980, 6, 24),
        birth_time=time(10, 0),
        birth_place="Moscow",
        latitude=Decimal("55.7558"),
        longitude=Decimal("37.6173"),
        timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


async def test_create_get_roundtrip(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    qa = await create_qa(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        question="What is my purpose?",
        lang="ru",
    )
    assert qa.status == "pending"

    reloaded = await get_qa(session, qa.id)
    assert reloaded.id == qa.id
    assert reloaded.question == "What is my purpose?"
    assert reloaded.lang == "ru"
    assert reloaded.status == "pending"


async def test_get_qa_missing_raises(session, default_tenant):
    with pytest.raises(NotFoundError):
        await get_qa(session, 999999)


async def test_list_qa_newest_first(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    q1 = await create_qa(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        question="first",
        lang="ru",
    )
    q2 = await create_qa(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        question="second",
        lang="ru",
    )

    rows = await list_qa(session, account_id=acc.id)
    assert [r.id for r in rows] == [q2.id, q1.id]


async def test_set_qa_status_done(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)
    qa = await create_qa(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        question="q",
        lang="ru",
    )

    await set_qa_status(session, qa.id, "done", answer_md="A", llm_tokens_in=5)
    reloaded = await get_qa(session, qa.id)
    assert reloaded.status == "done"
    assert reloaded.answer_md == "A"
    assert reloaded.llm_tokens_in == 5
    assert reloaded.completed_at is not None


async def test_resolve_calc_md_uses_existing_blueprint(session, default_tenant):
    from quantuum.db.models import Blueprint

    acc, profile = await _account_and_profile(session, default_tenant.id)
    bp = Blueprint(
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        status="done",
        calc_md="# Quantuum Blueprint — existing",
    )
    session.add(bp)
    await session.commit()
    await session.refresh(bp)

    calc_md, blueprint_id = await resolve_calc_md(
        session, account_id=acc.id, natal_profile_id=profile.id
    )
    assert calc_md == "# Quantuum Blueprint — existing"
    assert blueprint_id == bp.id


async def test_resolve_calc_md_builds_from_profile(session, default_tenant):
    acc, profile = await _account_and_profile(session, default_tenant.id)

    calc_md, blueprint_id = await resolve_calc_md(
        session, account_id=acc.id, natal_profile_id=profile.id
    )
    assert blueprint_id is None
    assert calc_md.startswith("# Quantuum Blueprint —")
