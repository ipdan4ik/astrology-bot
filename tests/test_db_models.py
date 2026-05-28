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


async def test_reading_model_create_and_load(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile, Reading
    from datetime import date, time

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="r1")
    profile = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id,
        full_name="Test", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile); await session.commit(); await session.refresh(profile)

    reading = Reading(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, kind="bazi", lang="ru",
    )
    session.add(reading); await session.commit(); await session.refresh(reading)
    assert reading.id is not None
    assert reading.status == "pending"
    assert reading.kind == "bazi"


async def test_reading_accepts_draw_jsonb(session, default_tenant):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile, Reading

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="1001"
    )
    profile = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    await session.flush()

    r = Reading(
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        kind="tarot",
        lang="en",
        draw_jsonb={"question": "Is this a test?", "cards": []},
    )
    session.add(r)
    await session.flush()

    reloaded = await session.get(Reading, r.id)
    assert reloaded.draw_jsonb == {"question": "Is this a test?", "cards": []}


async def test_reading_draw_jsonb_default_none(session, default_tenant):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile, Reading

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="2001"
    )
    profile = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    await session.flush()

    r = Reading(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, kind="bazi",
    )
    session.add(r)
    await session.flush()
    assert (await session.get(Reading, r.id)).draw_jsonb is None
