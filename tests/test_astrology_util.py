from quantuum.astrology.util import (
    norm360, to_sign_degree, fmt_deg, reduce_numerology, js_round, to_fixed,
    ELEMENTS, MODALITIES, SIGN_NAMES,
)


def test_norm360_wraps_negatives():
    assert norm360(-5) == 355
    assert norm360(365) == 5
    assert norm360(0) == 0


def test_js_round_is_half_up():
    assert js_round(0.5) == 1
    assert js_round(2.5) == 3
    assert js_round(-0.5) == 0
    assert js_round(1.4999) == 1


def test_to_fixed_matches_js():
    assert to_fixed(55.7558, 4) == "55.7558"
    assert to_fixed(2.0, 2) == "2.00"
    assert to_fixed(0.123, 2) == "0.12"


def test_to_sign_degree_anna_sun():
    sd = to_sign_degree(92.91)
    assert sd.sign == "Cancer"
    assert sd.degree == 2
    assert fmt_deg(to_sign_degree(92.91)).startswith("♋ Cancer 02°")


def test_reduce_numerology_keeps_master():
    assert reduce_numerology(29) == 11
    assert reduce_numerology(38) == 11
    assert reduce_numerology(39) == 3
    assert reduce_numerology(11, keep_master=False) == 2


def test_element_modality_tables_complete():
    assert ELEMENTS["Aries"] == "Fire"
    assert MODALITIES["Cancer"] == "Cardinal"
    assert len(ELEMENTS) == 12 and len(MODALITIES) == 12 and len(SIGN_NAMES) == 12
