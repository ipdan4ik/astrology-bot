from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import NatalProfile, Reading
from quantuum.tasks.reading import reading_generate


async def _seed_reading(session, default_tenant, *, kind: str, draw_jsonb=None):
    from datetime import date, time
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id=f"u_{kind}"
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
        natal_profile_id=profile.id, kind=kind, lang="en",
        draw_jsonb=draw_jsonb,
    )
    session.add(r)
    await session.commit()
    return r


async def test_reading_generate_branches_for_tarot(session, default_tenant, monkeypatch):
    draw = {
        "question": "test", "cards": [
            {"id": "major_00_fool", "reversed": False, "position": "past"},
            {"id": "major_01_magician", "reversed": False, "position": "present"},
            {"id": "major_02_high_priestess", "reversed": False, "position": "future"},
        ],
    }
    r = await _seed_reading(session, default_tenant, kind="tarot", draw_jsonb=draw)

    called = {"from_natal_profile": False}

    def _spy(*a, **kw):
        called["from_natal_profile"] = True
        raise AssertionError("from_natal_profile should not be called for tarot")

    # Patch the name as bound inside quantuum.tasks.reading (which did
    # `from quantuum.astrology.blueprint import from_natal_profile`), not the
    # source module attribute — otherwise the spy is never triggered.
    monkeypatch.setattr("quantuum.tasks.reading.from_natal_profile", _spy)
    from quantuum.tasks import delivery as delivery_mod
    monkeypatch.setattr(delivery_mod, "deliver_via_tenant_bot", AsyncMock())

    from quantuum.db.session import get_sessionmaker
    ctx = {"sessionmaker": get_sessionmaker(), "llm_client": None}
    await reading_generate(ctx, r.id)

    assert called["from_natal_profile"] is False
    reloaded = await session.get(Reading, r.id)
    await session.refresh(reloaded)
    assert reloaded.status == "done"
    assert reloaded.calc_md is not None and "The Fool" in reloaded.calc_md


async def test_reading_generate_chart_kind_still_works(session, default_tenant, monkeypatch):
    r = await _seed_reading(session, default_tenant, kind="bazi")
    from quantuum.tasks import delivery as delivery_mod
    monkeypatch.setattr(delivery_mod, "deliver_via_tenant_bot", AsyncMock())

    from quantuum.db.session import get_sessionmaker
    ctx = {"sessionmaker": get_sessionmaker(), "llm_client": None}
    await reading_generate(ctx, r.id)

    reloaded = await session.get(Reading, r.id)
    await session.refresh(reloaded)
    assert reloaded.status == "done"


async def test_reading_generate_iching_renders_hexagram(session, default_tenant, monkeypatch):
    draw = {
        "question": None,
        "lines": [7, 7, 7, 7, 7, 7],
        "primary_id": 1,
        "transformed_id": None,
        "changing_indices": [],
    }
    r = await _seed_reading(session, default_tenant, kind="iching", draw_jsonb=draw)

    from quantuum.tasks import delivery as delivery_mod
    monkeypatch.setattr(delivery_mod, "deliver_via_tenant_bot", AsyncMock())

    from quantuum.db.session import get_sessionmaker
    ctx = {"sessionmaker": get_sessionmaker(), "llm_client": None}
    await reading_generate(ctx, r.id)

    reloaded = await session.get(Reading, r.id)
    await session.refresh(reloaded)
    assert reloaded.status == "done"
    assert "The Creative" in reloaded.calc_md
