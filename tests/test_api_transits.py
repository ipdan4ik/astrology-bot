from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import AccountBalance, Request, TransitReport
from quantuum.domain.natal_profiles import upsert_natal_profile


@pytest_asyncio.fixture
async def spy_enqueue(monkeypatch):
    spy = AsyncMock()
    from quantuum.tasks import enqueue as enqueue_mod

    monkeypatch.setattr(enqueue_mod, "enqueue_transit", spy)
    return spy


@pytest_asyncio.fixture
async def client(engine, default_tenant, spy_enqueue):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_account(session, tenant_id, tg_user_id="1"):
    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg_user_id)


def _headers(acc, tenant_id):
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, tenant_id, False)}"}


async def _add_profile(session, tenant_id, account_id):
    return await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=account_id, full_name="Anna",
        birth_date=date(1990, 6, 15), birth_time=time(14, 30), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6176"), timezone="Europe/Moscow",
    )


async def _add_quota(session, account_id, credits=3):
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
    bal.free_trial_used = True
    bal.package_credits = credits
    session.add(bal)
    await session.commit()


async def test_transits_requires_natal_profile(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_quota(session, acc.id)
    r = await client.post("/v1/me/transits", json={}, headers=_headers(acc, default_tenant.id))
    assert r.status_code == 404


async def test_transits_requires_quota(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    # zero out welcome credits so the account has no quota
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = 0
    session.add(bal)
    await session.commit()
    r = await client.post("/v1/me/transits", json={}, headers=_headers(acc, default_tenant.id))
    assert r.status_code == 402


async def test_transits_create_happy(client, session, default_tenant, spy_enqueue):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)

    r = await client.post("/v1/me/transits", json={}, headers=_headers(acc, default_tenant.id))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    report_id = body["id"]

    row = await session.get(TransitReport, report_id)
    assert row is not None and row.window_days == 90

    reqs = (await session.execute(select(Request).where(Request.account_id == acc.id))).scalars().all()
    assert len(reqs) == 1 and reqs[0].kind == "transit"
    spy_enqueue.assert_awaited_once_with(report_id, None, reqs[0].id)


async def test_transits_window_clamped(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)
    r = await client.post(
        "/v1/me/transits", json={"window_days": 9999}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 202
    row = await session.get(TransitReport, r.json()["id"])
    assert row.window_days == 180


async def test_transits_get_own(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)
    created = await client.post("/v1/me/transits", json={"window_days": 30}, headers=_headers(acc, default_tenant.id))
    report_id = created.json()["id"]

    r = await client.get(f"/v1/me/transits/{report_id}", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == report_id
    assert body["window_days"] == 30
    assert body["report_md"] is None
    assert body["status"] == "pending"


async def test_transits_get_cross_account_404(client, session, default_tenant):
    owner = await _make_account(session, default_tenant.id, tg_user_id="1")
    await _add_profile(session, default_tenant.id, owner.id)
    await _add_quota(session, owner.id)
    created = await client.post("/v1/me/transits", json={}, headers=_headers(owner, default_tenant.id))
    report_id = created.json()["id"]

    other = await _make_account(session, default_tenant.id, tg_user_id="2")
    r = await client.get(f"/v1/me/transits/{report_id}", headers=_headers(other, default_tenant.id))
    assert r.status_code == 404


async def test_transits_get_missing_404(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    r = await client.get("/v1/me/transits/99999", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 404


async def test_transits_list_newest_first(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id, credits=5)
    first = await client.post("/v1/me/transits", json={}, headers=_headers(acc, default_tenant.id))
    second = await client.post("/v1/me/transits", json={}, headers=_headers(acc, default_tenant.id))

    r = await client.get("/v1/me/transits", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [second.json()["id"], first.json()["id"]]


async def test_transits_enqueue_failure_refunds(client, session, default_tenant, spy_enqueue):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id, credits=2)
    spy_enqueue.side_effect = RuntimeError("redis down")

    r = await client.post("/v1/me/transits", json={}, headers=_headers(acc, default_tenant.id))
    assert r.status_code == 503
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == 2  # refunded
