from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.profile import profile_to_kwargs, save_field
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile


async def _acc_with_profile(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="77")
    await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    return acc


async def test_profile_to_kwargs_roundtrip(session, default_tenant):
    acc = await _acc_with_profile(session, default_tenant.id)
    profile = await get_natal_profile(session, acc.id)
    kw = profile_to_kwargs(profile)
    assert kw["full_name"] == "Anna"
    assert kw["birth_time"] == time(10, 0)
    assert kw["latitude"] == Decimal("55.7558")


async def test_save_field_updates_one_field(session, default_tenant):
    acc = await _acc_with_profile(session, default_tenant.id)
    err_key = await save_field(session, account=acc, field="birth_time", raw="07:45")
    assert err_key is None
    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_time == time(7, 45)
    assert profile.full_name == "Anna"  # others untouched


async def test_save_field_invalid_returns_error_key(session, default_tenant):
    acc = await _acc_with_profile(session, default_tenant.id)
    err_key = await save_field(session, account=acc, field="birth_time", raw="bad")
    assert err_key == "profile.error.birth_time_invalid"


async def test_save_field_no_profile_returns_not_found_key(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="404"
    )
    err_key = await save_field(session, account=acc, field="birth_time", raw="07:45")
    assert err_key == "profile.not_found"
