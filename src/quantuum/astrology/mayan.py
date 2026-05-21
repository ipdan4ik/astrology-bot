"""Mayan Tzolkin: 260-day calendar = 20 day-signs x 13 tones (galactic numbers).

Ported from mayan.ts — behavior must match exactly.

Reference correlation: GMT 584283 (modified) — i.e. 11 Aug 3114 BCE Long
Count zero. The Tzolkin position on a Gregorian date is derived from the
Julian Day Number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Day-sign tables
# ---------------------------------------------------------------------------

TZOLKIN_SIGNS: list[str] = [
    "Imix", "Ik", "Akbal", "Kan", "Chicchan",
    "Cimi", "Manik", "Lamat", "Muluc", "Oc",
    "Chuen", "Eb", "Ben", "Ix", "Men",
    "Cib", "Caban", "Etznab", "Cauac", "Ahau",
]

# Dreamspell day signs (newer system — names slightly different).
DREAMSPELL_SIGNS: list[str] = [
    "Red Dragon", "White Wind", "Blue Night", "Yellow Seed", "Red Serpent",
    "White World-Bridger", "Blue Hand", "Yellow Star", "Red Moon", "White Dog",
    "Blue Monkey", "Yellow Human", "Red Skywalker", "White Wizard", "Blue Eagle",
    "Yellow Warrior", "Red Earth", "White Mirror", "Blue Storm", "Yellow Sun",
]


# ---------------------------------------------------------------------------
# Julian Day Number
# ---------------------------------------------------------------------------

def julian_day_number(dt: datetime) -> int:
    """Return the Julian Day Number for a UTC datetime.

    Uses the Fliegel-Van Flandern formula, matching Math.floor in mayan.ts.
    For all positive intermediate values (dates after ~4713 BCE) Python's ``//``
    integer floor division is identical to ``Math.floor``.
    """
    utc = dt.astimezone(timezone.utc)
    y = utc.year
    m = utc.month
    d = utc.day

    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = (
        d
        + (153 * mm + 2) // 5
        + 365 * yy
        + yy // 4
        - yy // 100
        + yy // 400
        - 32045
    )
    return jdn


# ---------------------------------------------------------------------------
# Tzolkin dataclass + calculator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tzolkin:
    trecena: int        # 1..13 (galactic tone)
    sign_index: int     # 0..19
    sign_name: str      # classic Maya
    dreamspell_name: str
    full: str
    kin: int            # 1..260


def tzolkin(dt: datetime) -> Tzolkin:
    """Return the Tzolkin position for the given datetime."""
    jdn = julian_day_number(dt)

    # Days since GMT correlation epoch (JDN 584283 = 4 Ahau, tone 4, sign 19).
    offset = jdn - 584283

    # sign index: (offset + 19) mod 20 — guards handle negative offsets
    sign_index = ((offset % 20) + 19 + 20) % 20
    # tone (trecena): epoch tone is 4 → shift = 3
    trecena = (((offset % 13) + 3) % 13 + 13) % 13 + 1
    # kin 1..260 — epoch kin = 160 (4 Ahau)
    kin = ((((offset % 260) + 159) % 260) + 260) % 260 + 1

    return Tzolkin(
        trecena=trecena,
        sign_index=sign_index,
        sign_name=TZOLKIN_SIGNS[sign_index],
        dreamspell_name=DREAMSPELL_SIGNS[sign_index],
        full=f"{trecena} {TZOLKIN_SIGNS[sign_index]}",
        kin=kin,
    )
