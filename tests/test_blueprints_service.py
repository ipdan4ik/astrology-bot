from quantuum.domain.blueprints import create_blueprint, get_blueprint, set_status
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD


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


def test_mock_blueprint_nonempty():
    assert MOCK_BLUEPRINT_MD.startswith("#")
    assert len(MOCK_BLUEPRINT_MD) > 200


async def test_create_and_transition(session, default_tenant):
    acc, profile = await _profile(session, default_tenant.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
    )
    assert bp.status == "pending"

    await set_status(session, bp.id, "done", llm_md=MOCK_BLUEPRINT_MD)
    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.llm_md == MOCK_BLUEPRINT_MD
    assert reloaded.completed_at is not None


async def test_natal_profile_upsert(session, default_tenant):
    from datetime import date, time
    from decimal import Decimal

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="42")
    assert await get_natal_profile(session, acc.id) is None

    data = dict(
        full_name="Anna",
        birth_date=date(1980, 6, 24),
        birth_time=time(10, 0),
        birth_place="Moscow",
        latitude=Decimal("55.7558"),
        longitude=Decimal("37.6173"),
        timezone="Europe/Moscow",
    )
    p1 = await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, **data
    )
    data["full_name"] = "Anna B"
    p2 = await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, **data
    )
    assert p1.id == p2.id
    assert p2.full_name == "Anna B"
