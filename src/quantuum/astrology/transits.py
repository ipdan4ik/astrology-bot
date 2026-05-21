"""Forward-window transit computation.

Pure (no DB). Reuses astro.py for all astronomy. Times are tz-aware UTC.

Exact transits are found with a daily-grid sample + bisection on a signed-offset
crossing function (see the plan's "crossing function" note): for an aspect branch
theta_b in {+theta, -theta}, offset(lon) = ((lon - n - theta_b + 180) % 360) - 180
is zero exactly at the aspect and changes sign through it (conjunction/opposition
included). The sawtooth wrap is filtered by requiring abs(f1 - f0) < 180.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from quantuum.astrology.astro import (
    ascendant_longitude,
    ecliptic_longitude,
    lunar_nodes,
    midheaven_longitude,
    planet_position,
)
from quantuum.astrology.blueprint import ALL_PLANETS, BlueprintInput, parse_birth_instant
from quantuum.astrology.util import fmt_deg, to_fixed, to_sign_degree

# Transiting bodies scanned for the forward forecast. Moon EXCLUDED (~13 deg/day
# -> noise); it still appears in the "current sky" table and as a natal target.
TRANSIT_FORECAST_BODIES: tuple[str, ...] = (
    "Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
)

# "Current sky" snapshot includes all ten (blueprint.ALL_PLANETS order).
CURRENT_SKY_BODIES: tuple[str, ...] = tuple(ALL_PLANETS)

# Natal points used as aspect targets (planets + Asc + MC + North Node).
NATAL_TARGETS: tuple[str, ...] = (*ALL_PLANETS, "Asc", "MC", "NN")

# Major aspects only, with tight transit orbs. Insertion order = tie-break priority.
TRANSIT_ASPECTS: dict[str, dict[str, float]] = {
    "Conjunction": {"angle": 0.0, "orb": 3.0},
    "Opposition": {"angle": 180.0, "orb": 3.0},
    "Trine": {"angle": 120.0, "orb": 3.0},
    "Square": {"angle": 90.0, "orb": 3.0},
    "Sextile": {"angle": 60.0, "orb": 2.0},
}

GRID_STEP_HOURS = 24
BISECTION_ITERS = 40
DEFAULT_WINDOW_DAYS = 90
MIN_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 180


def _sep180(a: float, b: float) -> float:
    """Angular separation folded to 0..180 (same convention as astro.find_aspect)."""
    return abs(((a - b + 540) % 360) - 180)


def clamp_window(days: object) -> int:
    """Coerce *days* to an int in [MIN_WINDOW_DAYS, MAX_WINDOW_DAYS]; default if invalid."""
    try:
        d = int(days)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS
    return max(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, d))


def compute_natal_targets(inp: BlueprintInput) -> dict[str, float]:
    """Natal ecliptic longitudes for every NATAL_TARGETS point (fixed for the window)."""
    birth = parse_birth_instant(inp)
    out: dict[str, float] = {p: planet_position(p, birth).longitude for p in ALL_PLANETS}
    out["Asc"] = ascendant_longitude(birth, inp.latitude, inp.longitude)
    out["MC"] = midheaven_longitude(birth, inp.longitude)
    out["NN"] = lunar_nodes(birth)["north"].longitude
    return out


@dataclass(frozen=True)
class SkyPosition:
    body: str
    longitude: float
    retrograde: bool


@dataclass(frozen=True)
class TransitHit:
    body: str       # transiting body
    target: str     # natal point
    aspect: str     # aspect name
    exact_at: datetime
    retrograde: bool  # transiting body retrograde at exact_at


@dataclass(frozen=True)
class ActiveAspect:
    body: str
    target: str
    aspect: str
    orb: float
    applying: bool
    exact_at: datetime | None  # nearest future exact within the window, if any


@dataclass(frozen=True)
class TransitReport:
    as_of: datetime
    window_days: int
    sky: list[SkyPosition]
    active: list[ActiveAspect]
    upcoming: list[TransitHit]
