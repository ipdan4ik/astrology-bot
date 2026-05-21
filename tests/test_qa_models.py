async def _profile(session, tenant_id):
    from datetime import date, time
    from decimal import Decimal

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="9")
    profile = NatalProfile(
        tenant_id=tenant_id,
        account_id=acc.id,
        full_name="Test User",
        birth_date=date(1990, 1, 1),
        birth_time=time(12, 0),
        birth_place="Moscow",
        latitude=Decimal("55.75"),
        longitude=Decimal("37.61"),
        timezone="Europe/Moscow",
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return acc, profile


async def test_qa_answer_defaults(session, default_tenant):
    from quantuum.db.models import QaAnswer

    acc, profile = await _profile(session, default_tenant.id)
    qa = QaAnswer(
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        question="x",
    )
    session.add(qa)
    await session.commit()
    await session.refresh(qa)

    assert qa.id is not None
    assert qa.status == "pending"
    assert qa.answer_md is None
    assert qa.created_at is not None
    assert qa.completed_at is None
