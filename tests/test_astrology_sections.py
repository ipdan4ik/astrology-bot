from datetime import datetime, timezone

import pytest

from quantuum.astrology.blueprint import BlueprintInput
from quantuum.astrology.sections import (
    BLUEPRINT_SECTION_ORDER,
    build_aspects_section,
    build_bazi_section,
    build_blueprint_context,
    build_gene_keys_section,
    build_human_design_section,
    build_identity_section,
    build_mayan_section,
    build_numerology_section,
    build_vedic_section,
)


def _sample_input() -> BlueprintInput:
    return BlueprintInput(
        full_name="Desmond Test",
        birth_date="1990-08-15",
        birth_time="14:30",
        birth_place="Moscow, RU",
        latitude=55.7558,
        longitude=37.6173,
        timezone="Europe/Moscow",
        for_year=2026,
    )


def test_blueprint_context_exposes_required_fields():
    ctx = build_blueprint_context(_sample_input())
    assert isinstance(ctx.birth, datetime)
    assert ctx.birth.tzinfo == timezone.utc
    assert set(ctx.planets) >= {"Sun", "Moon", "Mercury", "Mars"}
    assert len(ctx.ws_houses) == 12
    assert len(ctx.porphyry_houses) == 12
    assert ctx.for_year == 2026
    assert ctx.aspect_rows  # non-empty


SECTION_HEADINGS = {
    "astrology":    "## 1. Identity Layer",
    "aspects":      "## 2. Major Aspects",
    "vedic":        "## 3. Vedic (Sidereal, Lahiri Ayanamsha)",
    "numerology":   "## 4. Numerology (Pythagorean)",
    "bazi":         "## 5. Chinese Zodiac — Four Pillars (BaZi)",
    "human_design": "## 6. Human Design",
    "gene_keys":    "## 7. Gene Keys — The Activation Sequence",
    "mayan":        "## 8. Mayan Tzolkin (Traditional GMT correlation + Dreamspell label)",
}

@pytest.mark.parametrize("kind,expected_heading", SECTION_HEADINGS.items())
def test_section_starts_with_expected_heading(kind, expected_heading):
    inp = _sample_input()
    ctx = build_blueprint_context(inp)
    builders = {
        "astrology":    build_identity_section,
        "aspects":      build_aspects_section,
        "vedic":        build_vedic_section,
        "numerology":   build_numerology_section,
        "bazi":         build_bazi_section,
        "human_design": build_human_design_section,
        "gene_keys":    build_gene_keys_section,
        "mayan":        build_mayan_section,
    }
    md = builders[kind](inp, ctx)
    assert md.splitlines()[0] == expected_heading


def test_section_order_is_canonical():
    assert BLUEPRINT_SECTION_ORDER == (
        "astrology", "aspects", "vedic", "numerology",
        "bazi", "human_design", "gene_keys", "mayan",
    )
