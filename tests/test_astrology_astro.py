from datetime import datetime, timezone

from quantuum.astrology.astro import (
    ascendant_longitude,
    find_aspect,
    lunar_nodes,
    midheaven_longitude,
    nakshatra,
    planet_position,
    sidereal_longitude,
)
from quantuum.astrology.util import fmt_deg, to_sign_degree

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)
LAT, LON = 55.7558, 37.6173


def test_anna_planets():
    cases = {
        "Sun": ("♋ Cancer 02°54'36\"", False),
        "Moon": ("♏ Scorpio 14°27'08\"", False),
        "Mercury": ("♋ Cancer 24°27'01\"", False),
        "Venus": ("♊ Gemini 19°10'08\"", True),
        "Mars": ("♍ Virgo 21°10'24\"", False),
        "Jupiter": ("♍ Virgo 05°00'40\"", False),
        "Saturn": ("♍ Virgo 21°05'41\"", False),
        "Uranus": ("♏ Scorpio 22°01'50\"", True),
        "Neptune": ("♐ Sagittarius 20°58'18\"", True),
        "Pluto": ("♎ Libra 18°58'29\"", True),
    }
    for body, (deg, retro) in cases.items():
        p = planet_position(body, ANNA)
        assert fmt_deg(p) == deg, body
        assert p.retrograde is retro, body


def test_anna_angles():
    asc = ascendant_longitude(ANNA, LAT, LON)
    mc = midheaven_longitude(ANNA, LON)
    assert fmt_deg(to_sign_degree(asc)) == "♍ Virgo 06°53'56\""
    assert fmt_deg(to_sign_degree(mc)) == "♉ Taurus 27°28'49\""


def test_anna_nodes():
    nodes = lunar_nodes(ANNA)
    assert fmt_deg(nodes["north"]) == "♌ Leo 22°36'58\""
    assert fmt_deg(nodes["south"]) == "♒ Aquarius 22°36'58\""


def test_anna_sidereal_and_nakshatra():
    # Golden "## 3. Vedic" — sidereal Moon and its nakshatra.
    moon = planet_position("Moon", ANNA)
    sid_moon = sidereal_longitude(moon.longitude, ANNA)
    assert fmt_deg(to_sign_degree(sid_moon)) == "♎ Libra 20°52'03\""
    nak = nakshatra(sid_moon)
    assert nak["name"] == "Vishakha"
    assert nak["index"] == 16
    assert nak["pada"] == 1


def test_anna_first_aspect():
    # Golden "## 2. Major Aspects" first row: Sun-Jupiter Sextile, orb 2.10°.
    sun = planet_position("Sun", ANNA)
    jup = planet_position("Jupiter", ANNA)
    asp = find_aspect(sun.longitude, jup.longitude)
    assert asp is not None
    assert asp["name"] == "Sextile"
    assert round(asp["orb"], 2) == 2.10
