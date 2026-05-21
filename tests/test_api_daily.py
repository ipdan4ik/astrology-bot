from datetime import date, time, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, DailyHoroscope, NatalProfile
from quantuum.domain.natal_profiles import upsert_natal_profile


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _account(session, tenant_id, tg="1", *, subscriber=False, profile=False):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    if profile:
        await upsert_natal_profile(
            session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
            birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
            latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
        )
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    return acc


def _headers(acc, tenant_id):
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, tenant_id, False)}"}


async def test_get_daily_defaults(client, session, default_tenant):
    acc = await _account(session, default_tenant.id)
    r = await client.get("/v1/me/daily", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["send_hour"] == 9 and body["last_sent_on"] is None


async def test_put_enable_requires_subscription(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=False)
    r = await client.put(
        "/v1/me/daily", json={"enabled": True, "send_hour": 8}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 403


async def test_put_enable_as_subscriber(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=True)
    r = await client.put(
        "/v1/me/daily", json={"enabled": True, "send_hour": 8}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True and r.json()["send_hour"] == 8


async def test_put_disable_allowed_for_non_subscriber(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=False)
    r = await client.put(
        "/v1/me/daily", json={"enabled": False, "send_hour": 9}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


async def test_put_bad_hour_422(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=True)
    r = await client.put(
        "/v1/me/daily", json={"enabled": True, "send_hour": 25}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 422


async def test_list_horoscopes_newest_first(client, session, default_tenant):
    acc = await _account(session, default_tenant.id, subscriber=True, profile=True)
    profile = (await session.execute(
        select(NatalProfile).where(NatalProfile.account_id == acc.id)
    )).scalars().first()
    a = DailyHoroscope(tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
                       local_date=date(2026, 3, 1), status="done", horoscope_md="one")
    session.add(a)
    await session.commit()
    b = DailyHoroscope(tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id,
                       local_date=date(2026, 3, 2), status="done", horoscope_md="two")
    session.add(b)
    await session.commit()

    r = await client.get("/v1/me/daily/horoscopes", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [b.id, a.id]
