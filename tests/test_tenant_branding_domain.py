import asyncio

import pytest
from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import Tenant, TenantStringOverride
from quantuum.domain.tenant_branding import (
    BRANDING_I18N_KEYS,
    MAX_DISPLAY_NAME_LEN,
    MAX_HELP_LEN,
    MAX_SIGNATURE_LEN,
    MAX_WELCOME_LEN,
    get_branding_text,
    reset_branding_text,
    set_branding_text,
    set_display_name,
)


def test_branding_i18n_keys_inventory():
    assert set(BRANDING_I18N_KEYS) == {
        "start.welcome",
        "help.text",
        "brand.signature",
    }


def test_length_limits_inventory():
    assert MAX_DISPLAY_NAME_LEN == 64
    assert MAX_WELCOME_LEN == 2000
    assert MAX_HELP_LEN == 2000
    assert MAX_SIGNATURE_LEN == 200


async def test_get_returns_none_when_no_override(session, default_tenant):
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="start.welcome", lang="ru"
        )
        is None
    )


async def test_set_then_get_round_trip(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b1"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="ru",
        text="Привет от бренда",
        by_account_id=acc.id,
    )
    await session.commit()
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="start.welcome", lang="ru"
        )
        == "Привет от бренда"
    )


async def test_set_upsert_overwrites_text(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b2"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="help.text",
        lang="en",
        text="v1",
        by_account_id=acc.id,
    )
    await session.commit()
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="help.text",
        lang="en",
        text="v2",
        by_account_id=acc.id,
    )
    await session.commit()
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="help.text", lang="en"
        )
        == "v2"
    )


async def test_set_unknown_key_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b3"
    )
    with pytest.raises(ValueError, match="unknown branding key"):
        await set_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="not.a.real.key",
            lang="ru",
            text="x",
            by_account_id=acc.id,
        )


async def test_set_empty_text_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b4"
    )
    with pytest.raises(ValueError, match="empty"):
        await set_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="start.welcome",
            lang="ru",
            text="",
            by_account_id=acc.id,
        )


async def test_set_too_long_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b5"
    )
    too_long = "x" * (MAX_SIGNATURE_LEN + 1)
    with pytest.raises(ValueError, match="too long"):
        await set_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="brand.signature",
            lang="ru",
            text=too_long,
            by_account_id=acc.id,
        )


async def test_reset_deletes_row(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b6"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© Brand",
        by_account_id=acc.id,
    )
    await session.commit()
    await reset_branding_text(
        session, tenant_id=default_tenant.id, key="brand.signature", lang="ru"
    )
    await session.commit()
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="brand.signature", lang="ru"
        )
        is None
    )


async def test_reset_is_idempotent(session, default_tenant):
    # No row exists; should not raise.
    await reset_branding_text(
        session, tenant_id=default_tenant.id, key="brand.signature", lang="ru"
    )
    await session.commit()


async def test_set_populates_updated_by_and_at(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b7"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="help.text",
        lang="ru",
        text="hello",
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantStringOverride).where(
                TenantStringOverride.tenant_id == default_tenant.id,
                TenantStringOverride.key == "help.text",
                TenantStringOverride.lang == "ru",
            )
        )
    ).scalar_one()
    assert row.updated_by_account_id == acc.id
    assert row.updated_at is not None


async def test_set_bumps_updated_at_on_update(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b8"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="en",
        text="v1",
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantStringOverride).where(
                TenantStringOverride.tenant_id == default_tenant.id,
                TenantStringOverride.key == "start.welcome",
                TenantStringOverride.lang == "en",
            )
        )
    ).scalar_one()
    t1 = row.updated_at

    await asyncio.sleep(0.01)

    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="en",
        text="v2",
        by_account_id=acc.id,
    )
    await session.commit()
    await session.refresh(row)
    assert row.updated_at > t1


async def test_set_display_name_updates_column(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b9"
    )
    await set_display_name(
        session,
        tenant_id=default_tenant.id,
        display_name="Mystic Oracle",
        by_account_id=acc.id,
    )
    await session.commit()
    row = await session.get(Tenant, default_tenant.id)
    assert row.display_name == "Mystic Oracle"


async def test_set_display_name_too_long_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b10"
    )
    too_long = "x" * (MAX_DISPLAY_NAME_LEN + 1)
    with pytest.raises(ValueError, match="too long"):
        await set_display_name(
            session,
            tenant_id=default_tenant.id,
            display_name=too_long,
            by_account_id=acc.id,
        )


async def test_set_display_name_empty_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b11"
    )
    with pytest.raises(ValueError, match="empty"):
        await set_display_name(
            session,
            tenant_id=default_tenant.id,
            display_name="",
            by_account_id=acc.id,
        )


async def test_set_display_name_with_newline_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b12"
    )
    with pytest.raises(ValueError, match="newline"):
        await set_display_name(
            session,
            tenant_id=default_tenant.id,
            display_name="bad\nname",
            by_account_id=acc.id,
        )


async def test_get_unknown_key_raises(session, default_tenant):
    with pytest.raises(ValueError, match="unknown branding key"):
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="not.a.real.key", lang="ru"
        )
