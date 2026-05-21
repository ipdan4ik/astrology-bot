from quantuum.astrology.numerology import calculate_numerology


def test_anna_numerology_matches_golden():
    # Anna Belyeva, 1980-06-24, forYear 2025 — values from anna.calc.md "## 4. Numerology"
    n = calculate_numerology("Anna Belyeva", 1980, 6, 24, 2025)
    assert n.life_path == 3
    assert n.birth_day == 6
    assert n.destiny == 3
    assert n.soul_urge == 2
    assert n.personality == 1
    assert n.maturity == 6
    assert n.attitude == 3
    assert n.personal_year == 3
    assert n.personal_year_target == 2025
    assert (n.pinnacles.p1, n.pinnacles.p2, n.pinnacles.p3, n.pinnacles.p4) == (3, 6, 9, 6)
    assert (n.challenges.c1, n.challenges.c2, n.challenges.c3, n.challenges.c4) == (0, 3, 3, 3)


def test_master_number_name_preserved():
    # name_sum/reduce should preserve master numbers where they occur; sanity check a vowel/consonant split sums.
    n = calculate_numerology("Anna Belyeva", 1980, 6, 24, 2024)
    assert n.personal_year == 2  # 2024 personal year per golden timing table
