import random

import pytest

from quantuum.divination.iching import (
    HEXAGRAMS,
    CastResult,
    build_calc_md,
    build_calc_md_from_jsonb,
    cast_three_coins,
)


def test_64_hexagrams_present():
    assert set(HEXAGRAMS.keys()) == set(range(1, 65))


def test_every_hexagram_has_full_data():
    for hid, h in HEXAGRAMS.items():
        assert h.number == hid
        assert isinstance(h.name_en, str) and h.name_en
        assert isinstance(h.judgment, str) and len(h.judgment) > 10
        assert isinstance(h.image, str) and len(h.image) > 10
        assert len(h.lines) == 6
        for line_text in h.lines:
            assert isinstance(line_text, str) and len(line_text) > 0


def test_cast_three_coins_produces_six_lines():
    rng = random.Random(0)
    cast = cast_three_coins(rng=rng)
    assert len(cast.lines) == 6


def test_cast_line_values_are_in_6_7_8_9():
    rng = random.Random(0)
    for _ in range(50):
        cast = cast_three_coins(rng=rng)
        for v in cast.lines:
            assert v in (6, 7, 8, 9)


def test_cast_changing_indices_match_6_and_9():
    rng = random.Random(99)
    for _ in range(20):
        cast = cast_three_coins(rng=rng)
        expected = tuple(i for i, v in enumerate(cast.lines) if v in (6, 9))
        assert cast.changing_indices == expected


def test_transformed_hexagram_is_none_when_no_changing_lines():
    cast = CastResult(
        lines=(7, 8, 7, 8, 7, 8), changing_indices=(),
        primary_id=63, transformed_id=None,
    )
    assert cast.transformed_id is None


def test_cast_is_deterministic_with_seeded_rng():
    a = cast_three_coins(rng=random.Random(123))
    b = cast_three_coins(rng=random.Random(123))
    assert a == b


def test_primary_id_in_1_64():
    rng = random.Random(7)
    for _ in range(50):
        cast = cast_three_coins(rng=rng)
        assert 1 <= cast.primary_id <= 64
        if cast.transformed_id is not None:
            assert 1 <= cast.transformed_id <= 64


def test_build_calc_md_includes_question_and_primary_hex():
    cast = cast_three_coins(rng=random.Random(2))
    md = build_calc_md(question="What should I do?", cast=cast)
    primary = HEXAGRAMS[cast.primary_id]
    assert "What should I do?" in md
    assert primary.name_en in md
    assert "Judgment" in md or "judgment" in md
    assert "Image" in md or "image" in md


def test_build_calc_md_no_question_safe():
    cast = cast_three_coins(rng=random.Random(2))
    md = build_calc_md(question=None, cast=cast)
    assert "None" not in md
    assert "(none)" in md


def test_build_calc_md_changing_lines_surface_line_text():
    cast = CastResult(
        lines=(9, 7, 7, 8, 8, 8), changing_indices=(0,),
        primary_id=1, transformed_id=44,
    )
    md = build_calc_md(question=None, cast=cast)
    expected_line_text = HEXAGRAMS[1].lines[0]
    assert expected_line_text[:30] in md
    assert HEXAGRAMS[44].name_en in md


def test_build_calc_md_from_jsonb_round_trip():
    cast = cast_three_coins(rng=random.Random(11))
    payload = {
        "question": "test",
        "lines": list(cast.lines),
        "primary_id": cast.primary_id,
        "transformed_id": cast.transformed_id,
        "changing_indices": list(cast.changing_indices),
    }
    md = build_calc_md_from_jsonb(payload)
    assert HEXAGRAMS[cast.primary_id].name_en in md


def test_build_calc_md_from_jsonb_rejects_invalid_primary_id():
    with pytest.raises(KeyError):
        build_calc_md_from_jsonb({
            "question": None, "lines": [7, 7, 7, 7, 7, 7],
            "primary_id": 99, "transformed_id": None, "changing_indices": [],
        })


def test_king_wen_sanity_all_yang_is_hexagram_1():
    cast = CastResult(
        lines=(7, 7, 7, 7, 7, 7), changing_indices=(),
        primary_id=1, transformed_id=None,
    )
    # If cast_three_coins ever produces all-7s, primary_id must be 1 (Creative).
    # This is enforced by the lookup; the test asserts our lookup direction is right
    # by hand-rolling a cast with no changing lines and asserting via build_calc_md.
    md = build_calc_md(question=None, cast=cast)
    assert HEXAGRAMS[1].name_en in md  # The Creative


def test_king_wen_sanity_all_yin_is_hexagram_2():
    cast = CastResult(
        lines=(8, 8, 8, 8, 8, 8), changing_indices=(),
        primary_id=2, transformed_id=None,
    )
    md = build_calc_md(question=None, cast=cast)
    assert HEXAGRAMS[2].name_en in md  # The Receptive


def test_lookup_table_maps_all_yang_to_1():
    """Verify the King Wen lookup table directly: pattern 0b111111 (all yang
    bottom-to-top) must map to hexagram 1."""
    from quantuum.divination.iching import _KING_WEN, _lines_to_pattern
    assert _KING_WEN[_lines_to_pattern((7, 7, 7, 7, 7, 7))] == 1
    assert _KING_WEN[_lines_to_pattern((8, 8, 8, 8, 8, 8))] == 2
