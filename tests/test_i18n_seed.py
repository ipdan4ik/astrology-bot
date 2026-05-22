"""Tests for i18n seed: platform strings and tenant default language bootstrap."""

from sqlmodel import select

from quantuum.db.models import PlatformString, TenantLanguage
from quantuum.i18n.seed_strings import BASE_STRINGS


async def test_ensure_base_strings_seeds_all(session):
    from quantuum.db.bootstrap import ensure_base_strings

    await ensure_base_strings(session)

    result = await session.execute(select(PlatformString))
    seeded = {(row.key, row.lang) for row in result.scalars()}

    for key, langs in BASE_STRINGS.items():
        for lang in langs:
            assert (key, lang) in seeded, f"Missing ({key!r}, {lang!r}) in platform_strings"


async def test_ensure_base_strings_non_destructive(session):
    """Pre-existing rows must survive a re-seed (admin edits not overwritten)."""
    from quantuum.db.bootstrap import ensure_base_strings

    # Insert one row with an edited text before seeding
    edited_text = "CUSTOM EDITED TEXT — should not be overwritten"
    first_key = next(iter(BASE_STRINGS))
    first_lang = next(iter(BASE_STRINGS[first_key]))
    session.add(PlatformString(key=first_key, lang=first_lang, text=edited_text))
    await session.commit()

    await ensure_base_strings(session)

    result = await session.execute(
        select(PlatformString).where(
            PlatformString.key == first_key,
            PlatformString.lang == first_lang,
        )
    )
    row = result.scalar_one()
    assert row.text == edited_text, "ensure_base_strings must not overwrite existing rows"


async def test_ensure_base_strings_idempotent(session):
    """Running twice must not raise and must not create duplicate rows."""
    from quantuum.db.bootstrap import ensure_base_strings

    await ensure_base_strings(session)
    await ensure_base_strings(session)  # second run — must be idempotent

    result = await session.execute(select(PlatformString))
    rows = list(result.scalars())
    pairs = [(row.key, row.lang) for row in rows]
    assert len(pairs) == len(set(pairs)), "Duplicate (key, lang) rows found after idempotent re-seed"

    # Total count must match exactly what BASE_STRINGS defines
    expected = sum(len(langs) for langs in BASE_STRINGS.values())
    assert len(rows) == expected


async def test_ensure_tenant_default_language(session, default_tenant):
    """ensure_tenant_default_language seeds ru (default) + en (extra) idempotently."""
    from quantuum.db.bootstrap import ensure_tenant_default_language

    tenant_id = default_tenant.id

    await ensure_tenant_default_language(session, tenant_id)

    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows = {row.lang: row for row in result.scalars()}

    assert "ru" in rows, "ru language row missing"
    assert rows["ru"].is_default is True, "ru must be the default language"
    assert rows["ru"].enabled is True

    assert "en" in rows, "en language row missing"
    assert rows["en"].is_default is False, "en must NOT be the default"
    assert rows["en"].enabled is True

    # Exactly one default row
    defaults = [r for r in rows.values() if r.is_default]
    assert len(defaults) == 1, f"Expected exactly 1 default language, got {len(defaults)}"

    # --- Idempotency: run again; no error, no duplicates, no default flip ---
    await ensure_tenant_default_language(session, tenant_id)

    result2 = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows2 = list(result2.scalars())
    assert len(rows2) == 2, f"Expected 2 language rows after re-run, got {len(rows2)}"
    defaults2 = [r for r in rows2 if r.is_default]
    assert len(defaults2) == 1 and defaults2[0].lang == "ru"


async def test_platform_tenant_default_language_seeded(session):
    """Bootstrap must seed the platform tenant's default language (ru) too."""
    from quantuum.db.bootstrap import (
        ensure_platform_tenant,
        ensure_tenant_default_language,
    )

    platform = await ensure_platform_tenant(session)
    await ensure_tenant_default_language(session, platform.id, default_lang="ru")

    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == platform.id)
    )
    rows = list(result.scalars())
    defaults = [r for r in rows if r.is_default]
    assert len(defaults) == 1, (
        f"Expected exactly 1 default language for platform tenant, got {len(defaults)}"
    )
    assert defaults[0].lang == "ru"


def test_place_edit_strings_present_and_obsolete_removed():
    from quantuum.i18n.seed_strings import BASE_STRINGS

    for key in [
        "profile.place.confirm",
        "profile.place.not_found",
        "profile.kb.place_confirm",
        "profile.kb.place_retry",
    ]:
        assert key in BASE_STRINGS, f"missing {key}"
        assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key]

    # The repurposed place prompt now mentions geolocation.
    assert "геопозиц" in BASE_STRINGS["profile.prompt.birth_place"]["ru"].lower()

    for key in [
        "profile.coords",
        "profile.timezone",
        "profile.kb.edit_coords",
        "profile.kb.edit_timezone",
        "profile.prompt.coords",
        "profile.prompt.timezone",
        "profile.error.coords_invalid",
        "profile.error.timezone_invalid",
    ]:
        assert key not in BASE_STRINGS, f"obsolete key still present: {key}"
