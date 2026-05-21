from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, NatalProfile
from quantuum.domain.daily import (
    claim_horoscope,
    due_daily_account_ids,
    get_settings,
    get_tg_chat_id,
    is_subscriber,
    list_horoscopes,
    mark_sent,
    set_horoscope_status,
    upsert_settings,
)


async def _account(session, tenant_id, tg_user_id, *, tz="Europe/Moscow", subscriber=True):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg_user_id)
    session.add(NatalProfile(
        tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone=tz,
    ))
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    return acc


async def test_is_subscriber(session, default_tenant):
    sub = await _account(session, default_tenant.id, "1", subscriber=True)
    non = await _account(session, default_tenant.id, "2", subscriber=False)
    assert await is_subscriber(session, sub.id) is True
    assert await is_subscriber(session, non.id) is False


async def test_upsert_and_get_settings(session, default_tenant):
    acc = await _account(session, default_tenant.id, "3")
    assert await get_settings(session, acc.id) is None
    row = await upsert_settings(
        session, tenant_id=default_tenant.id, account_id=acc.id, enabled=True, send_hour=8
    )
    assert row.enabled is True and row.send_hour == 8
    again = await upsert_settings(
        session, tenant_id=default_tenant.id, account_id=acc.id, enabled=True, send_hour=21
    )
    assert again.send_hour == 21
    fetched = await get_settings(session, acc.id)
    assert fetched.send_hour == 21


async def test_claim_horoscope_is_idempotent(session, default_tenant):
    acc = await _account(session, default_tenant.id, "4")
    profile = (await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == acc.id)
    )).scalars().first()
    first = await claim_horoscope(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, local_date=date(2026, 3, 1), lang="ru",
    )
    assert first is not None and first.status == "generating"
    second = await claim_horoscope(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, local_date=date(2026, 3, 1), lang="ru",
    )
    assert second is None


async def test_set_status_and_list(session, default_tenant):
    acc = await _account(session, default_tenant.id, "5")
    profile = (await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == acc.id)
    )).scalars().first()
    r1 = await claim_horoscope(session, tenant_id=default_tenant.id, account_id=acc.id,
                               natal_profile_id=profile.id, local_date=date(2026, 3, 1), lang="ru")
    r2 = await claim_horoscope(session, tenant_id=default_tenant.id, account_id=acc.id,
                               natal_profile_id=profile.id, local_date=date(2026, 3, 2), lang="ru")
    await set_horoscope_status(session, r1.id, "done", horoscope_md="hi", llm_tokens_in=3)
    await session.refresh(r1)
    assert r1.status == "done" and r1.horoscope_md == "hi" and r1.completed_at is not None
    rows = await list_horoscopes(session, account_id=acc.id)
    assert [r.id for r in rows] == [r2.id, r1.id]  # newest-first


async def test_mark_sent(session, default_tenant):
    acc = await _account(session, default_tenant.id, "6")
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=acc.id, enabled=True, send_hour=9)
    await mark_sent(session, acc.id, date(2026, 3, 1))
    settings = await get_settings(session, acc.id)
    assert settings.last_sent_on == date(2026, 3, 1)


async def test_get_tg_chat_id(session, default_tenant):
    acc = await _account(session, default_tenant.id, "777")
    chat = await get_tg_chat_id(session, acc.id)
    assert chat == "777"  # find_or_create_account_by_tg stored provider_user_id="777"


async def test_due_daily_account_ids_selection(session, default_tenant):
    # now = 06:00 UTC -> Moscow (UTC+3) local 09:00.
    now = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)

    due_acc = await _account(session, default_tenant.id, "10", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=due_acc.id, enabled=True, send_hour=9)

    wrong_hour = await _account(session, default_tenant.id, "11", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=wrong_hour.id, enabled=True, send_hour=10)

    already = await _account(session, default_tenant.id, "12", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=already.id, enabled=True, send_hour=9)
    await mark_sent(session, already.id, date(2026, 3, 1))  # already sent today (local)

    non_sub = await _account(session, default_tenant.id, "13", tz="Europe/Moscow", subscriber=False)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=non_sub.id, enabled=True, send_hour=9)

    disabled = await _account(session, default_tenant.id, "14", tz="Europe/Moscow", subscriber=True)
    await upsert_settings(session, tenant_id=default_tenant.id, account_id=disabled.id, enabled=False, send_hour=9)

    due = await due_daily_account_ids(session, now=now)
    assert due_acc.id in due
    assert wrong_hour.id not in due
    assert already.id not in due
    assert non_sub.id not in due
    assert disabled.id not in due
