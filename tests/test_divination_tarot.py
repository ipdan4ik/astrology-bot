import random

import pytest

from quantuum.divination.tarot import (
    TAROT_DECK,
    CardDraw,
    build_calc_md,
    build_calc_md_from_jsonb,
    draw_three,
)


def test_deck_has_78_cards():
    assert len(TAROT_DECK) == 78


def test_deck_has_22_majors():
    majors = [c for c in TAROT_DECK if c.arcana == "major"]
    assert len(majors) == 22


def test_deck_has_four_suits_of_14():
    for suit in ("wands", "cups", "swords", "pentacles"):
        suit_cards = [c for c in TAROT_DECK if c.suit == suit]
        assert len(suit_cards) == 14, f"suit {suit} has {len(suit_cards)} cards"


def test_all_card_ids_are_unique():
    ids = [c.id for c in TAROT_DECK]
    assert len(set(ids)) == 78


def test_every_card_has_keywords():
    for c in TAROT_DECK:
        assert len(c.upright) >= 3, f"{c.id} upright"
        assert len(c.reversed) >= 3, f"{c.id} reversed"


def test_draw_three_returns_three_distinct_cards():
    rng = random.Random(42)
    cards = draw_three(rng=rng)
    assert len(cards) == 3
    ids = [d.card.id for d in cards]
    assert len(set(ids)) == 3


def test_draw_three_positions_are_past_present_future():
    rng = random.Random(42)
    cards = draw_three(rng=rng)
    assert [d.position for d in cards] == ["past", "present", "future"]


def test_draw_three_is_deterministic_with_seeded_rng():
    a = draw_three(rng=random.Random(123))
    b = draw_three(rng=random.Random(123))
    assert [(d.card.id, d.reversed, d.position) for d in a] == \
           [(d.card.id, d.reversed, d.position) for d in b]


def test_reversal_distribution_is_roughly_uniform():
    rng = random.Random(7)
    reversed_count = 0
    total = 0
    for _ in range(500):
        for d in draw_three(rng=rng):
            reversed_count += int(d.reversed)
            total += 1
    assert 600 < reversed_count < 900


def test_build_calc_md_includes_question_and_all_three_cards():
    cards = [
        CardDraw(card=TAROT_DECK[0], reversed=False, position="past"),
        CardDraw(card=TAROT_DECK[1], reversed=True, position="present"),
        CardDraw(card=TAROT_DECK[2], reversed=False, position="future"),
    ]
    md = build_calc_md(question="Will I find love?", cards=cards)
    assert "Will I find love?" in md
    assert TAROT_DECK[0].name in md
    assert TAROT_DECK[1].name in md
    assert TAROT_DECK[2].name in md
    assert "reversed" in md.lower()


def test_build_calc_md_no_question_renders_placeholder():
    cards = [
        CardDraw(card=TAROT_DECK[0], reversed=False, position="past"),
        CardDraw(card=TAROT_DECK[1], reversed=False, position="present"),
        CardDraw(card=TAROT_DECK[2], reversed=False, position="future"),
    ]
    md = build_calc_md(question=None, cards=cards)
    assert "None" not in md  # don't render the literal Python None
    assert "(none)" in md  # explicit placeholder is present


def test_build_calc_md_from_jsonb_round_trip():
    rng = random.Random(11)
    cards = draw_three(rng=rng)
    payload = {
        "question": "test",
        "cards": [
            {"id": d.card.id, "reversed": d.reversed, "position": d.position}
            for d in cards
        ],
    }
    md = build_calc_md_from_jsonb(payload)
    for d in cards:
        assert d.card.name in md


def test_build_calc_md_from_jsonb_rejects_unknown_card_id():
    payload = {"question": None, "cards": [
        {"id": "bogus_xx", "reversed": False, "position": "past"},
        {"id": "major_00_fool", "reversed": False, "position": "present"},
        {"id": "major_01_magician", "reversed": False, "position": "future"},
    ]}
    with pytest.raises(KeyError):
        build_calc_md_from_jsonb(payload)
