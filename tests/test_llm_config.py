"""Tests for the DB-backed LLM config domain + admin routes (Plan 5d, Task 6)."""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from quantuum.api.app import create_app
from quantuum.auth import jwt_tokens
from quantuum.db.models import Account, AccountIdentity, AuditLog


# ---------------------------------------------------------------------------
# Domain tests
# ---------------------------------------------------------------------------


async def test_get_llm_config_returns_settings_defaults(session):
    """No PlatformConfig rows → returns the env-derived defaults."""
    from quantuum.domain.llm_config import get_llm_config
    from quantuum.settings import get_settings

    s = get_settings()
    cfg = await get_llm_config(session)

    assert cfg["provider"] == s.llm_provider
    assert cfg["model"] == s.llm_model
    assert cfg["temperature"] == s.llm_temperature
    assert cfg["max_tokens"] == s.llm_max_tokens


async def test_set_llm_config_overrides_and_types_are_coerced(session):
    """set_llm_config stores overrides; get_llm_config applies coercion."""
    from quantuum.domain.llm_config import get_llm_config, set_llm_config
    from quantuum.settings import get_settings

    s = get_settings()

    # Set model and temperature, leave provider/max_tokens at defaults.
    result = await set_llm_config(session, model="claude-x", temperature=0.5)
    await session.commit()

    cfg = await get_llm_config(session)

    assert cfg["model"] == "claude-x"
    assert cfg["temperature"] == 0.5
    # Types coerced correctly
    assert isinstance(cfg["temperature"], float)
    assert isinstance(cfg["max_tokens"], int)
    # Non-overridden fields stay at defaults
    assert cfg["provider"] == s.llm_provider
    assert cfg["max_tokens"] == s.llm_max_tokens

    # set_llm_config return value also reflects the new config
    assert result["model"] == "claude-x"
    assert result["temperature"] == 0.5


async def test_set_llm_config_update_existing(session):
    """Calling set_llm_config twice on the same field updates, not duplicates."""
    from quantuum.domain.llm_config import get_llm_config, set_llm_config

    await set_llm_config(session, model="first-model")
    await session.commit()

    await set_llm_config(session, model="second-model")
    await session.commit()

    cfg = await get_llm_config(session)
    assert cfg["model"] == "second-model"


# ---------------------------------------------------------------------------
# Route fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Route tests — GET /admin/platform/llm
# ---------------------------------------------------------------------------


async def test_get_llm_config_route_returns_defaults(client, sa_headers):
    """GET returns provider/model/temperature/max_tokens + api_key_configured bool."""
    from quantuum.settings import get_settings

    s = get_settings()
    r = await client.get("/admin/platform/llm", headers=sa_headers)
    assert r.status_code == 200
    body = r.json()

    assert body["provider"] == s.llm_provider
    assert body["model"] == s.llm_model
    assert body["temperature"] == s.llm_temperature
    assert body["max_tokens"] == s.llm_max_tokens
    # api_key_configured is a bool reflecting bool(llm_api_key)
    assert isinstance(body["api_key_configured"], bool)
    # NEVER expose the actual key
    assert "api_key" not in body


async def test_get_llm_config_route_customer_forbidden(client, customer_headers):
    r = await client.get("/admin/platform/llm", headers=customer_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Route tests — PUT /admin/platform/llm
# ---------------------------------------------------------------------------


async def test_put_llm_config_updates_and_returns_config(client, sa_headers):
    r = await client.put(
        "/admin/platform/llm",
        json={"model": "claude-db-model", "temperature": 0.3},
        headers=sa_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "claude-db-model"
    assert body["temperature"] == 0.3
    assert "api_key" not in body
    assert "api_key_configured" in body

    # Subsequent GET sees the change
    r2 = await client.get("/admin/platform/llm", headers=sa_headers)
    assert r2.json()["model"] == "claude-db-model"
    assert r2.json()["temperature"] == 0.3


async def test_put_llm_config_records_audit(client, sa_headers, session):
    r = await client.put(
        "/admin/platform/llm",
        json={"model": "test-model", "max_tokens": 5000},
        headers=sa_headers,
    )
    assert r.status_code == 200

    result = await session.execute(
        select(AuditLog).where(AuditLog.action == "platform.llm.update")
    )
    rows = result.scalars().all()
    assert len(rows) >= 1
    row = rows[-1]
    assert row.entity_type == "platform_config"
    assert row.payload_jsonb.get("model") == "test-model"
    assert row.payload_jsonb.get("max_tokens") == 5000


async def test_put_llm_config_customer_forbidden(client, customer_headers):
    r = await client.put(
        "/admin/platform/llm",
        json={"model": "hack"},
        headers=customer_headers,
    )
    assert r.status_code == 403


async def test_put_llm_config_ignores_none_fields(client, sa_headers):
    """Omitted fields stay at defaults; only provided fields are stored."""
    from quantuum.settings import get_settings

    s = get_settings()
    r = await client.put(
        "/admin/platform/llm",
        json={"model": "only-model"},
        headers=sa_headers,
    )
    assert r.status_code == 200
    body = r.json()
    # Provided field updated
    assert body["model"] == "only-model"
    # Omitted fields stay at settings defaults
    assert body["temperature"] == s.llm_temperature
    assert body["max_tokens"] == s.llm_max_tokens
