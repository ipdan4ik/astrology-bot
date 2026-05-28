import pytest

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.tenant_features import (
    FEATURE_KEYS,
    is_feature_enabled,
    list_feature_states,
    set_feature_enabled,
)


def test_feature_keys_inventory():
    # Lock the canonical flag set (SP2 12 + SP4 referrals + SP5 gifts + SP6 tarot/iching).
    assert set(FEATURE_KEYS) == {
        "qa", "blueprint", "transits", "daily",
        "reading.bazi", "reading.numerology", "reading.human_design",
        "reading.astrology", "reading.vedic", "reading.gene_keys",
        "reading.mayan", "reading.aspects",
        "reading.tarot", "reading.iching",
        "referrals",
        "gifts",
    }
    assert len(FEATURE_KEYS) == 16


async def test_is_feature_enabled_defaults_true_when_no_row(session, default_tenant):
    assert await is_feature_enabled(session, default_tenant.id, "qa") is True
    assert await is_feature_enabled(session, default_tenant.id, "reading.bazi") is True


async def test_set_then_read_false_round_trip(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="qa",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    assert await is_feature_enabled(session, default_tenant.id, "qa") is False


async def test_set_back_to_true_restores(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor2"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="qa",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="qa",
        enabled=True,
        by_account_id=acc.id,
    )
    await session.commit()
    assert await is_feature_enabled(session, default_tenant.id, "qa") is True


async def test_set_unknown_key_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor3"
    )
    with pytest.raises(ValueError, match="not.a.real.key"):
        await set_feature_enabled(
            session,
            tenant_id=default_tenant.id,
            key="not.a.real.key",
            enabled=False,
            by_account_id=acc.id,
        )


async def test_list_feature_states_returns_all_twelve(session, default_tenant):
    states = await list_feature_states(session, default_tenant.id)
    assert set(states.keys()) == set(FEATURE_KEYS)
    assert all(v is True for v in states.values())  # all default ON


async def test_list_reflects_overrides(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor4"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="daily",
        enabled=False,
        by_account_id=acc.id,
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="reading.bazi",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    states = await list_feature_states(session, default_tenant.id)
    assert states["daily"] is False
    assert states["reading.bazi"] is False
    assert states["qa"] is True
    assert states["reading.numerology"] is True
    assert len(states) == 16


async def test_set_populates_updated_by(session, default_tenant):
    from sqlalchemy import select

    from quantuum.db.models import TenantConfig

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor5"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="transits",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantConfig).where(
                TenantConfig.tenant_id == default_tenant.id,
                TenantConfig.key == "feature.transits",
            )
        )
    ).scalar_one()
    assert row.value_jsonb == {"enabled": False}
    assert row.updated_by_account_id == acc.id


async def test_set_bumps_updated_at_on_update(session, default_tenant):
    import asyncio

    from sqlalchemy import select

    from quantuum.db.models import TenantConfig

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor6"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="blueprint",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantConfig).where(
                TenantConfig.tenant_id == default_tenant.id,
                TenantConfig.key == "feature.blueprint",
            )
        )
    ).scalar_one()
    t1 = row.updated_at

    await asyncio.sleep(0.01)

    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="blueprint",
        enabled=True,
        by_account_id=acc.id,
    )
    await session.commit()
    await session.refresh(row)
    t2 = row.updated_at

    assert t2 > t1


async def test_is_feature_enabled_unknown_key_raises(session, default_tenant):
    with pytest.raises(ValueError, match=r"not\.a\.real\.key"):
        await is_feature_enabled(session, default_tenant.id, "not.a.real.key")
