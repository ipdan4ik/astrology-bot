from quantuum.db import models


def test_all_tables_registered():
    names = set(models.SQLModel.metadata.tables.keys())
    assert {
        "tenants",
        "accounts",
        "account_identities",
        "account_refresh_tokens",
        "natal_profiles",
        "blueprints",
        "requests",
        "account_balance",
    } <= names


def test_blueprint_defaults():
    bp = models.Blueprint(tenant_id=1, account_id=1, natal_profile_id=1)
    assert bp.status == "pending"
    assert bp.calc_md is None


async def test_default_tenant_fixture(default_tenant):
    assert default_tenant.id is not None
    assert default_tenant.slug == "default"


async def test_bootstrap_seeds_default_tenant(session):
    from quantuum.db.bootstrap import ensure_default_tenant
    from quantuum.domain.tenants import get_default_tenant_id

    t1 = await ensure_default_tenant(session)
    t2 = await ensure_default_tenant(session)  # idempotent
    assert t1.id == t2.id
    assert await get_default_tenant_id(session) == t1.id


def test_tenant_bot_and_role_tables_registered():
    names = set(models.SQLModel.metadata.tables.keys())
    assert {"tenant_bots", "tenant_roles"} <= names


def test_tenant_has_tenancy_fields():
    t = models.Tenant(slug="x", display_name="X")
    assert t.tier == "basic"
    assert t.is_platform is False
    assert t.primary_owner_account_id is None


def test_tenant_bot_defaults():
    tb = models.TenantBot(tenant_id=1, bot_token_enc=b"x", webhook_secret_path="s")
    assert tb.transport == "polling"
    assert tb.status == "active"
    assert tb.bot_telegram_id is None
