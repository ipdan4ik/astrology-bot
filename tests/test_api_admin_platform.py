import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import Account, AccountIdentity, AuditLog, Tenant


@pytest_asyncio.fixture
async def client(engine, default_tenant):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def sa_headers(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, None, True)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer_headers(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    token = jwt_tokens.issue_access_token(acc.id, default_tenant.id, False)
    return {"Authorization": f"Bearer {token}"}


async def test_create_and_list_invite(client, sa_headers):
    r = await client.post(
        "/admin/platform/invites",
        json={"tier": "basic", "max_uses": 2},
        headers=sa_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["code"]
    assert body["deeplink"].endswith(body["code"])
    assert body["tier"] == "basic"

    lst = await client.get("/admin/platform/invites", headers=sa_headers)
    assert lst.status_code == 200
    assert any(i["code"] == body["code"] for i in lst.json())


async def test_revoke_invite(client, sa_headers):
    created = await client.post("/admin/platform/invites", json={}, headers=sa_headers)
    invite_id = created.json()["id"]
    r = await client.post(f"/admin/platform/invites/{invite_id}/revoke", headers=sa_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


async def test_list_tenants(client, sa_headers, default_tenant):
    r = await client.get("/admin/platform/tenants", headers=sa_headers)
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()}
    assert "default" in slugs


async def test_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/invites", headers=customer_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Task 14 — platform config
# ---------------------------------------------------------------------------


async def test_config_put_then_get_roundtrip(client, sa_headers):
    r = await client.put(
        "/admin/platform/config",
        json={"key": "feature_x", "value": {"enabled": True, "limit": 5}},
        headers=sa_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"key": "feature_x", "value": {"enabled": True, "limit": 5}}

    g = await client.get("/admin/platform/config", headers=sa_headers)
    assert g.status_code == 200
    assert g.json()["feature_x"] == {"enabled": True, "limit": 5}


async def test_config_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/config", headers=customer_headers)
    assert r.status_code == 403
    p = await client.put(
        "/admin/platform/config",
        json={"key": "k", "value": {}},
        headers=customer_headers,
    )
    assert p.status_code == 403


# ---------------------------------------------------------------------------
# Task 14 — platform strings (+ invalidate_i18n_all is effective)
# ---------------------------------------------------------------------------


async def test_strings_put_then_get(client, sa_headers):
    r = await client.put(
        "/admin/platform/strings",
        json={"key": "greeting", "lang": "en", "text": "Hi there"},
        headers=sa_headers,
    )
    assert r.status_code == 200
    assert r.json() == {"key": "greeting", "lang": "en", "text": "Hi there"}

    g = await client.get("/admin/platform/strings?lang=en", headers=sa_headers)
    assert g.status_code == 200
    rows = g.json()
    assert any(
        row["key"] == "greeting" and row["text"] == "Hi there" and row["lang"] == "en"
        for row in rows
    )


async def test_strings_put_invalidates_cache_globally(
    client, sa_headers, session, default_tenant
):
    """Warm the i18n cache for a tenant, then PUT a NEW platform string via the
    API. invalidate_i18n_all must clear the warmed cache so t() returns it."""
    from quantuum.db.models import TenantLanguage
    from quantuum.i18n.resolver import t

    session.add(
        TenantLanguage(
            tenant_id=default_tenant.id, lang="en", enabled=True, is_default=True
        )
    )
    await session.commit()

    # Warm the cache (cold build, "newkey" absent)
    missing = await t(session, "newkey", "en", tenant_id=default_tenant.id)
    assert missing == "[missing: newkey]"

    # PUT a new platform string via the API
    r = await client.put(
        "/admin/platform/strings",
        json={"key": "newkey", "lang": "en", "text": "Brand New"},
        headers=sa_headers,
    )
    assert r.status_code == 200

    # Cache was cleared globally -> resolver rebuilds and sees the new string
    resolved = await t(session, "newkey", "en", tenant_id=default_tenant.id)
    assert resolved == "Brand New"


async def test_strings_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/strings?lang=en", headers=customer_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Task 14 — superadmins
# ---------------------------------------------------------------------------


async def test_superadmins_list_includes_seeded(client, sa_headers):
    r = await client.get("/admin/platform/superadmins", headers=sa_headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["email"] == "root@x.com" for row in rows)


async def test_superadmin_grant_and_revoke(client, sa_headers, session, default_tenant):
    fresh = Account(tenant_id=default_tenant.id, is_superadmin=False)
    session.add(fresh)
    await session.commit()
    await session.refresh(fresh)

    g = await client.post(
        "/admin/platform/superadmins",
        json={"account_id": fresh.id},
        headers=sa_headers,
    )
    assert g.status_code == 200
    assert g.json()["account_id"] == fresh.id

    lst = await client.get("/admin/platform/superadmins", headers=sa_headers)
    assert any(row["account_id"] == fresh.id for row in lst.json())

    d = await client.delete(
        f"/admin/platform/superadmins/{fresh.id}", headers=sa_headers
    )
    assert d.status_code == 200
    assert d.json() == {"ok": True}

    lst2 = await client.get("/admin/platform/superadmins", headers=sa_headers)
    assert all(row["account_id"] != fresh.id for row in lst2.json())


async def test_superadmin_grant_missing_account_404(client, sa_headers):
    r = await client.post(
        "/admin/platform/superadmins",
        json={"account_id": 999999},
        headers=sa_headers,
    )
    assert r.status_code == 404


async def test_superadmin_cannot_revoke_last(client, sa_headers, session):
    # Only one superadmin exists (the seeded one) -> get its id and try to revoke
    result = await session.execute(
        select(Account).where(Account.is_superadmin == True)  # noqa: E712
    )
    sas = result.scalars().all()
    assert len(sas) == 1
    last_id = sas[0].id

    r = await client.delete(
        f"/admin/platform/superadmins/{last_id}", headers=sa_headers
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Task 15 — tenant suspend / archive
# ---------------------------------------------------------------------------


async def test_suspend_then_archive_tenant(client, sa_headers, session):
    tenant = Tenant(slug="suspendme", display_name="Suspend Me")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    s = await client.post(
        f"/admin/platform/tenants/{tenant.id}/suspend", headers=sa_headers
    )
    assert s.status_code == 200
    await session.refresh(tenant)
    assert tenant.status == "suspended"

    a = await client.post(
        f"/admin/platform/tenants/{tenant.id}/archive", headers=sa_headers
    )
    assert a.status_code == 200
    await session.refresh(tenant)
    assert tenant.status == "archived"

    # audit entries recorded with tenant_id None (platform action)
    audits = await session.execute(
        select(AuditLog).where(
            AuditLog.action.in_(["platform.tenant.suspend", "platform.tenant.archive"])
        )
    )
    actions = {a.action for a in audits.scalars()}
    assert actions == {"platform.tenant.suspend", "platform.tenant.archive"}


async def test_suspend_platform_tenant_400(client, sa_headers, session):
    platform = Tenant(slug="platform", display_name="Platform", is_platform=True)
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    s = await client.post(
        f"/admin/platform/tenants/{platform.id}/suspend", headers=sa_headers
    )
    assert s.status_code == 400
    a = await client.post(
        f"/admin/platform/tenants/{platform.id}/archive", headers=sa_headers
    )
    assert a.status_code == 400


async def test_suspend_customer_forbidden(client, customer_headers, default_tenant):
    r = await client.post(
        f"/admin/platform/tenants/{default_tenant.id}/suspend",
        headers=customer_headers,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Task 15 — platform audit-log read
# ---------------------------------------------------------------------------


async def test_platform_audit_log_returns_entries_newest_first(
    client, sa_headers, session
):
    # generate some platform mutations
    await client.put(
        "/admin/platform/config",
        json={"key": "a", "value": {"x": 1}},
        headers=sa_headers,
    )
    await client.put(
        "/admin/platform/config",
        json={"key": "b", "value": {"x": 2}},
        headers=sa_headers,
    )

    r = await client.get("/admin/platform/audit-log", headers=sa_headers)
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 2
    # newest first: created_at descending
    times = [e["created_at"] for e in entries]
    assert times == sorted(times, reverse=True)
    assert any(e["action"] == "platform.config.update" for e in entries)


async def test_platform_audit_log_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/audit-log", headers=customer_headers)
    assert r.status_code == 403
