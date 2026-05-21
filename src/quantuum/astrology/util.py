"""Utility helpers shared by the astrology calculator modules.

Ported from util.ts — behavior must match exactly, including JS Math.round
semantics (half-up toward +∞) via js_round().
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Math constants
# ---------------------------------------------------------------------------

TWO_PI: float = math.pi * 2
DEG: float = math.pi / 180
RAD: float = 180 / math.pi

# ---------------------------------------------------------------------------
# JS-parity helpers
# ---------------------------------------------------------------------------


def js_round(x: float) -> int:
    """Round half-up toward +∞, matching JS Math.round exactly.

    Python's built-in round() uses banker's rounding (half-to-even);
    this function replicates the JS behaviour: floor(x + 0.5).
    """
    return math.floor(x + 0.5)


def to_fixed(x: float, n: int) -> str:
    """Format a float to n decimal places, matching JS Number.toFixed(n)."""
    return f"{x:.{n}f}"


# ---------------------------------------------------------------------------
# Angle normalisation
# ---------------------------------------------------------------------------


def norm360(x: float) -> float:
    """Normalise an angle to [0, 360)."""
    v = x % 360
    if v < 0:
        v += 360
    return v


def norm_rad(x: float) -> float:
    """Normalise an angle in radians to [0, TWO_PI)."""
    v = x % TWO_PI
    if v < 0:
        v += TWO_PI
    return v


# ---------------------------------------------------------------------------
# Sign tables
# ---------------------------------------------------------------------------

SIGN_NAMES: tuple[str, ...] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

SIGN_GLYPH: dict[str, str] = {
    "Aries": "♈",
    "Taurus": "♉",
    "Gemini": "♊",
    "Cancer": "♋",
    "Leo": "♌",
    "Virgo": "♍",
    "Libra": "♎",
    "Scorpio": "♏",
    "Sagittarius": "♐",
    "Capricorn": "♑",
    "Aquarius": "♒",
    "Pisces": "♓",
}

ELEMENTS: dict[str, str] = {
    "Aries": "Fire",
    "Leo": "Fire",
    "Sagittarius": "Fire",
    "Taurus": "Earth",
    "Virgo": "Earth",
    "Capricorn": "Earth",
    "Gemini": "Air",
    "Libra": "Air",
    "Aquarius": "Air",
    "Cancer": "Water",
    "Scorpio": "Water",
    "Pisces": "Water",
}

MODALITIES: dict[str, str] = {
    "Aries": "Cardinal",
    "Cancer": "Cardinal",
    "Libra": "Cardinal",
    "Capricorn": "Cardinal",
    "Taurus": "Fixed",
    "Leo": "Fixed",
    "Scorpio": "Fixed",
    "Aquarius": "Fixed",
    "Gemini": "Mutable",
    "Virgo": "Mutable",
    "Sagittarius": "Mutable",
    "Pisces": "Mutable",
}

# ---------------------------------------------------------------------------
# SignDegree dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignDegree:
    """Ecliptic position broken down into sign + degree/minute/second."""

    longitude: float  # normalised 0..360
    sign: str
    degree: int  # 0..29 degrees within sign
    minute: int  # 0..59
    second: int  # 0..59 (js_round of fractional seconds — may reach 60 edge case)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def to_sign_degree(longitude: float) -> SignDegree:
    """Convert an ecliptic longitude to a SignDegree."""
    lon = norm360(longitude)
    sign_index = math.floor(lon / 30)
    sign = SIGN_NAMES[sign_index]
    in_sign = lon - sign_index * 30
    degree = math.floor(in_sign)
    min_total = (in_sign - degree) * 60
    minute = math.floor(min_total)
    second = js_round((min_total - minute) * 60)
    return SignDegree(longitude=lon, sign=sign, degree=degree, minute=minute, second=second)


def fmt_deg(sd: SignDegree) -> str:
    """Format a SignDegree as a human-readable string, e.g. '♋ Cancer 02°54\'32\"'."""
    return f"{SIGN_GLYPH[sd.sign]} {sd.sign} {sd.degree:02d}°{sd.minute:02d}'{sd.second:02d}\""


# ---------------------------------------------------------------------------
# Numerology
# ---------------------------------------------------------------------------


def reduce_numerology(n: int, keep_master: bool = True) -> int:
    """Reduce a positive integer to a numerology digit.

    Preserves master numbers 11, 22, 33 when keep_master is True.
    Returns 0 for n <= 0.
    """
    if n <= 0:
        return 0
    while n > 9:
        if keep_master and (n == 11 or n == 22 or n == 33):
            return n
        s = 0
        x = n
        while x > 0:
            s += x % 10
            x = math.floor(x / 10)
        n = s
    return n
