from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def superadmin(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, None, True)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_calculate_and_mark_paid(client, superadmin, default_tenant):
    now = utcnow()
    start = (now - timedelta(days=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)
    r = await client.post(
        "/admin/platform/payouts/calculate",
        headers=superadmin,
        json={
            "tenant_id": default_tenant.id,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        },
    )
    assert r.status_code == 201
    payout_id = r.json()["id"]
    assert r.json()["status"] == "calculated"

    r2 = await client.get("/admin/platform/payouts", headers=superadmin)
    assert r2.status_code == 200
    assert any(p["id"] == payout_id for p in r2.json())

    r3 = await client.patch(
        f"/admin/platform/payouts/{payout_id}",
        headers=superadmin,
        json={"external_ref": "tx-9"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "paid"
    assert r3.json()["external_ref"] == "tx-9"


async def test_payouts_require_superadmin(client, customer, default_tenant):
    r = await client.get("/admin/platform/payouts", headers=customer)
    assert r.status_code == 403


async def test_mark_unknown_payout_404(client, superadmin):
    r = await client.patch(
        "/admin/platform/payouts/999999", headers=superadmin, json={"external_ref": "x"}
    )
    assert r.status_code == 404


async def test_calculate_invalid_period_400(client, superadmin, default_tenant):
    now = utcnow().replace(microsecond=0)
    r = await client.post(
        "/admin/platform/payouts/calculate",
        headers=superadmin,
        json={"tenant_id": default_tenant.id,
              "period_start": now.isoformat(), "period_end": now.isoformat()},
    )
    assert r.status_code == 400


async def test_calculate_duplicate_period_409(client, superadmin, default_tenant):
    from datetime import timedelta
    now = utcnow().replace(microsecond=0)
    start = (now - timedelta(days=2)).isoformat()
    end = now.isoformat()
    body = {"tenant_id": default_tenant.id, "period_start": start, "period_end": end}
    r1 = await client.post("/admin/platform/payouts/calculate", headers=superadmin, json=body)
    assert r1.status_code == 201
    r2 = await client.post("/admin/platform/payouts/calculate", headers=superadmin, json=body)
    assert r2.status_code == 409
