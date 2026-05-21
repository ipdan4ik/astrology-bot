from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import (
    AccountBalance,
    QaAnswer,
    Request,
)
from quantuum.domain.natal_profiles import upsert_natal_profile


@pytest_asyncio.fixture
async def spy_enqueue(monkeypatch):
    spy = AsyncMock()
    from quantuum.tasks import enqueue as enqueue_mod

    monkeypatch.setattr(enqueue_mod, "enqueue_qa", spy)
    return spy


@pytest_asyncio.fixture
async def client(engine, default_tenant, spy_enqueue):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_account(session, tenant_id, tg_user_id="1"):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg_user_id
    )
    return acc


def _headers(acc, tenant_id):
    return {"Authorization": f"Bearer {jwt_tokens.issue_access_token(acc.id, tenant_id, False)}"}


async def _add_profile(session, tenant_id, account_id):
    return await upsert_natal_profile(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        full_name="Anna",
        birth_date=date(1990, 6, 15),
        birth_time=time(14, 30),
        birth_place="Moscow",
        latitude=Decimal("55.7558"),
        longitude=Decimal("37.6176"),
        timezone="Europe/Moscow",
    )


async def _add_quota(session, account_id, credits=3):
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
    bal.free_trial_used = True
    bal.package_credits = credits
    session.add(bal)
    await session.commit()


async def test_qa_requires_natal_profile(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_quota(session, acc.id)
    r = await client.post(
        "/v1/me/qa", json={"question": "Will I be rich?"}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 404


async def test_qa_requires_quota(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    r = await client.post(
        "/v1/me/qa", json={"question": "Will I be rich?"}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 402


async def test_qa_create_happy(client, session, default_tenant, spy_enqueue):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)

    r = await client.post(
        "/v1/me/qa",
        json={"question": "Will I be rich?"},
        headers=_headers(acc, default_tenant.id),
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    qa_id = body["id"]

    # A QaAnswer row was created
    qa = await session.get(QaAnswer, qa_id)
    assert qa is not None
    assert qa.question == "Will I be rich?"

    # A Request(kind="qa") was created
    from sqlmodel import select

    requests = (
        await session.execute(select(Request).where(Request.account_id == acc.id))
    ).scalars().all()
    assert len(requests) == 1
    req = requests[0]
    assert req.kind == "qa"

    # enqueue_qa called with (qa_id, None, request_id)
    spy_enqueue.assert_awaited_once_with(qa_id, None, req.id)


async def test_qa_question_truncated(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)

    long_q = "a" * 1500
    r = await client.post(
        "/v1/me/qa", json={"question": long_q}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 202
    qa = await session.get(QaAnswer, r.json()["id"])
    assert len(qa.question) == 1000


async def test_qa_empty_question_rejected(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)

    r = await client.post(
        "/v1/me/qa", json={"question": "   "}, headers=_headers(acc, default_tenant.id)
    )
    assert r.status_code == 422


async def test_qa_get_own(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id)

    created = await client.post(
        "/v1/me/qa", json={"question": "Q1"}, headers=_headers(acc, default_tenant.id)
    )
    qa_id = created.json()["id"]

    r = await client.get(f"/v1/me/qa/{qa_id}", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == qa_id
    assert body["question"] == "Q1"
    assert body["answer_md"] is None
    assert body["status"] == "pending"


async def test_qa_get_cross_account_404(client, session, default_tenant):
    owner = await _make_account(session, default_tenant.id, tg_user_id="1")
    await _add_profile(session, default_tenant.id, owner.id)
    await _add_quota(session, owner.id)
    created = await client.post(
        "/v1/me/qa", json={"question": "Q1"}, headers=_headers(owner, default_tenant.id)
    )
    qa_id = created.json()["id"]

    other = await _make_account(session, default_tenant.id, tg_user_id="2")
    r = await client.get(f"/v1/me/qa/{qa_id}", headers=_headers(other, default_tenant.id))
    assert r.status_code == 404


async def test_qa_get_missing_404(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    r = await client.get("/v1/me/qa/99999", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 404


async def test_qa_list_newest_first(client, session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await _add_profile(session, default_tenant.id, acc.id)
    await _add_quota(session, acc.id, credits=5)

    first = await client.post(
        "/v1/me/qa", json={"question": "Q1"}, headers=_headers(acc, default_tenant.id)
    )
    second = await client.post(
        "/v1/me/qa", json={"question": "Q2"}, headers=_headers(acc, default_tenant.id)
    )
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    r = await client.get("/v1/me/qa", headers=_headers(acc, default_tenant.id))
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [second_id, first_id]
