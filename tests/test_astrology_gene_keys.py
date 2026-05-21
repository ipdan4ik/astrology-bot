from datetime import datetime, timezone

from quantuum.astrology.human_design import calculate_human_design
from quantuum.astrology.gene_keys import calculate_gene_keys

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)


def test_anna_gene_keys_match_golden():
    gk = calculate_gene_keys(calculate_human_design(ANNA))
    # Life's Work: 15.5, Flowering of Life, Dullness, Magnetism, Florescence
    assert (gk.lifes_work.gate, gk.lifes_work.line) == (15, 5)
    assert gk.lifes_work.name == "Flowering of Life"
    assert (gk.lifes_work.shadow, gk.lifes_work.gift, gk.lifes_work.siddhi) == ("Dullness", "Magnetism", "Florescence")
    # Evolution: 10.5, Naturalness, Self-Obsession, Naturalness, Being
    assert (gk.evolution.gate, gk.evolution.line) == (10, 5)
    assert gk.evolution.name == "Naturalness"
    assert (gk.evolution.shadow, gk.evolution.gift, gk.evolution.siddhi) == ("Self-Obsession", "Naturalness", "Being")
    # Radiance: 17.2, The Eye, Opinion, Far-sightedness, Omniscience
    assert (gk.radiance.gate, gk.radiance.line) == (17, 2)
    assert gk.radiance.name == "The Eye"
    assert (gk.radiance.shadow, gk.radiance.gift, gk.radiance.siddhi) == ("Opinion", "Far-sightedness", "Omniscience")
    # Purpose: 18.2, Healing Mind, Judgement, Integrity, Perfection
    assert (gk.purpose.gate, gk.purpose.line) == (18, 2)
    assert gk.purpose.name == "Healing Mind"
    assert (gk.purpose.shadow, gk.purpose.gift, gk.purpose.siddhi) == ("Judgement", "Integrity", "Perfection")


def test_all_64_hexagrams_present():
    from quantuum.astrology.gene_keys import GATE_TO_HEXAGRAM
    assert sorted(GATE_TO_HEXAGRAM.keys()) == list(range(1, 65))
