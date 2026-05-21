"""Western & Vedic astrology positions calculated from Astronomy Engine.

Ported from astro.ts — behavior must match exactly. Positions are geocentric,
true-of-date apparent. Houses use Whole Sign by default; Porphyry quadrant
cusps are also provided for reference.

JS->Python parity notes:
- The astronomy `Time` is built from the input datetime converted to UTC, passing
  sub-second precision through `second = dt.second + dt.microsecond / 1e6`, so it
  matches the JS `new Date(...)` instant exactly.
- The analytic formulas (mean lunar node, mean obliquity, Lahiri ayanamsha) do
  NOT use astronomy-engine — they are pure arithmetic on epoch-milliseconds,
  reproducing the JS `Date.getTime() - Date.UTC(...)` expressions. The JS
  `Date.UTC(1900, 0, 0, 12, 0, 0)` is 1899-12-31T12:00:00Z (month 0 = Jan,
  day 0 = Dec 31 of the prior year).
- Astronomy API attributes used: SunPosition(t).elon, EclipticGeoMoon(t).lon,
  Ecliptic(GeoVector(body, t, True)).elon, SiderealTime(t) (hours).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import astronomy

from .util import (
    DEG,
    RAD,
    SignDegree,
    norm360,
    to_sign_degree,
)

PlanetName = Literal[
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
]

# ---------------------------------------------------------------------------
# Epoch constants (reproducing JS Date.UTC expressions exactly)
# ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# Date.UTC(2000, 0, 1, 12, 0, 0) = 2000-01-01T12:00:00Z
_J2000_MS = (datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc) - _EPOCH).total_seconds() * 1000
# Date.UTC(1900, 0, 0, 12, 0, 0) = 1899-12-31T12:00:00Z (JS month 0=Jan, day 0=prev Dec 31)
_J1900_MS = (datetime(1899, 12, 31, 12, 0, 0, tzinfo=timezone.utc) - _EPOCH).total_seconds() * 1000


def _epoch_ms(dt: datetime) -> float:
    """Epoch-milliseconds for a datetime, matching JS Date.getTime()."""
    return (dt.astimezone(timezone.utc) - _EPOCH).total_seconds() * 1000


def _astro_time(dt: datetime) -> astronomy.Time:
    """Build an astronomy.Time from a datetime, treating the instant as UTC.

    Sub-second precision is preserved via the float `second` argument so the
    instant matches the JS `new Date(...)` exactly.
    """
    u = dt.astimezone(timezone.utc)
    return astronomy.Time.Make(
        u.year, u.month, u.day, u.hour, u.minute, u.second + u.microsecond / 1e6
    )


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """A planet position: a SignDegree plus a retrograde flag.

    Carries the same fields as SignDegree (longitude/sign/degree/minute/second)
    so fmt_deg(position) works directly, plus `retrograde`.
    """

    longitude: float
    sign: str
    degree: int
    minute: int
    second: int
    retrograde: bool


def _position_from(sd: SignDegree, retrograde: bool) -> Position:
    return Position(
        longitude=sd.longitude,
        sign=sd.sign,
        degree=sd.degree,
        minute=sd.minute,
        second=sd.second,
        retrograde=retrograde,
    )


# ---------------------------------------------------------------------------
# Body mapping
# ---------------------------------------------------------------------------

BODY_MAP: dict[str, object] = {
    "Sun": "sun",
    "Moon": "moon",
    "Mercury": astronomy.Body.Mercury,
    "Venus": astronomy.Body.Venus,
    "Mars": astronomy.Body.Mars,
    "Jupiter": astronomy.Body.Jupiter,
    "Saturn": astronomy.Body.Saturn,
    "Uranus": astronomy.Body.Uranus,
    "Neptune": astronomy.Body.Neptune,
    "Pluto": astronomy.Body.Pluto,
}


def ecliptic_longitude(body: PlanetName, dt: datetime) -> float:
    """Geocentric apparent ecliptic longitude (deg) for a given body."""
    code = BODY_MAP[body]
    t = _astro_time(dt)
    if code == "sun":
        return norm360(astronomy.SunPosition(t).elon)
    if code == "moon":
        return norm360(astronomy.EclipticGeoMoon(t).lon)
    # GeoVector returns J2000-equatorial vector; Ecliptic() converts to mean ecliptic of date.
    vec = astronomy.GeoVector(code, t, True)
    ecl = astronomy.Ecliptic(vec)
    return norm360(ecl.elon)


def planet_position(body: PlanetName, dt: datetime) -> Position:
    lon = ecliptic_longitude(body, dt)
    sd = to_sign_degree(lon)
    # Detect retrograde by sampling lon ~6h later.
    later = dt + timedelta(hours=6)
    lon2 = ecliptic_longitude(body, later)
    diff = ((lon2 - lon + 540) % 360) - 180  # signed angular delta
    return _position_from(sd, diff < 0)


# ---------------------------------------------------------------------------
# Lunar nodes
# ---------------------------------------------------------------------------


def mean_lunar_node_longitude(dt: datetime) -> float:
    """Mean lunar node (analytic series, IAU 2000-ish). Reference: Meeus ch. 47."""
    t = (_epoch_ms(dt) - _J2000_MS) / (86400 * 1000) / 36525
    omega = (
        125.0445479
        - 1934.1362891 * t
        + 0.0020754 * t * t
        + (t * t * t) / 467441
        - (t * t * t * t) / 60616000
    )
    return norm360(omega)


def lunar_nodes(dt: datetime) -> dict[str, SignDegree]:
    north = mean_lunar_node_longitude(dt)
    return {"north": to_sign_degree(north), "south": to_sign_degree(north + 180)}


# ---------------------------------------------------------------------------
# Sidereal time, obliquity, angles
# ---------------------------------------------------------------------------


def local_sidereal_time_deg(dt: datetime, longitude_deg: float) -> float:
    """Local Sidereal Time at the observer (degrees)."""
    gst_hours = astronomy.SiderealTime(_astro_time(dt))  # hours, 0..24
    gst_deg = gst_hours * 15
    return norm360(gst_deg + longitude_deg)


def mean_obliquity_deg(dt: datetime) -> float:
    """Mean obliquity of the ecliptic (degrees), Meeus formula."""
    t = (_epoch_ms(dt) - _J2000_MS) / (86400 * 1000) / 36525
    eps = 23.43929111 - 0.0130041667 * t - 1.6e-7 * t * t + 5.0361e-7 * t * t * t
    return eps


def ascendant_longitude(dt: datetime, lat_deg: float, lon_deg: float) -> float:
    """Ascendant (rising) longitude in degrees (Meeus AA p.99 / 13.1)."""
    lst = local_sidereal_time_deg(dt, lon_deg) * DEG
    eps = mean_obliquity_deg(dt) * DEG
    lat = lat_deg * DEG
    y = math.cos(lst)
    x = -(math.sin(eps) * math.tan(lat) + math.cos(eps) * math.sin(lst))
    return norm360(math.atan2(y, x) * RAD)


def midheaven_longitude(dt: datetime, lon_deg: float) -> float:
    """Midheaven (MC) longitude: tan(MC) = tan(LST) / cos(eps)."""
    lst = local_sidereal_time_deg(dt, lon_deg) * DEG
    eps = mean_obliquity_deg(dt) * DEG
    mc = math.atan2(math.sin(lst), math.cos(lst) * math.cos(eps)) * RAD
    # Bring MC into the same hemisphere as LST.
    if norm360(mc) - norm360(lst * RAD) > 180:
        mc -= 180
    return norm360(mc)


# ---------------------------------------------------------------------------
# Houses
# ---------------------------------------------------------------------------


def whole_sign_houses(asc_lon: float) -> list[float]:
    """Whole sign houses: house 1 starts at the sign of the Ascendant."""
    start_sign = math.floor(asc_lon / 30)
    return [norm360((start_sign + i) * 30) for i in range(12)]


def porphyry_cusps(asc: float, mc: float) -> list[float]:
    """Porphyry quadrant cusps: ASC/MC/DSC/IC exact, each quadrant in three equal arcs."""
    ic = norm360(mc + 180)
    dsc = norm360(asc + 180)
    arc1 = (asc - mc + 360) % 360  # MC -> ASC (12,11,10 region)
    arc2 = (ic - asc + 360) % 360  # ASC -> IC
    cusps = [0.0] * 12
    cusps[0] = asc
    cusps[1] = norm360(asc + arc2 / 3)
    cusps[2] = norm360(asc + (2 * arc2) / 3)
    cusps[3] = ic
    cusps[4] = norm360(ic + arc1 / 3)
    cusps[5] = norm360(ic + (2 * arc1) / 3)
    cusps[6] = dsc
    cusps[7] = norm360(dsc + arc2 / 3)
    cusps[8] = norm360(dsc + (2 * arc2) / 3)
    cusps[9] = mc
    cusps[10] = norm360(mc + arc1 / 3)
    cusps[11] = norm360(mc + (2 * arc1) / 3)
    return cusps


def placidus_cusps(dt: datetime, lat_deg: float, lon_deg: float) -> list[float]:
    """Quadrant house cusps (Porphyry division — see astro.ts rationale)."""
    asc_lon = ascendant_longitude(dt, lat_deg, lon_deg)
    mc = midheaven_longitude(dt, lon_deg)
    return porphyry_cusps(asc_lon, mc)


def house_of(longitude: float, cusps: list[float]) -> int:
    """House placement (1..12) for an ecliptic longitude given an array of cusps."""
    lon = norm360(longitude)
    for i in range(12):
        a = cusps[i]
        b = cusps[(i + 1) % 12]
        arc = (b - a + 360) % 360
        offset = (lon - a + 360) % 360
        if offset < arc or arc == 0:
            return i + 1
    return 12


# ---------------------------------------------------------------------------
# Aspects
# ---------------------------------------------------------------------------

AspectName = Literal[
    "Conjunction",
    "Opposition",
    "Trine",
    "Square",
    "Sextile",
    "Quincunx",
    "Semisquare",
    "Sesquisquare",
]

# Insertion order matters: find_aspect picks "first wins on ties".
ASPECTS: dict[str, dict[str, float]] = {
    "Conjunction": {"angle": 0, "orb": 8},
    "Opposition": {"angle": 180, "orb": 8},
    "Trine": {"angle": 120, "orb": 7},
    "Square": {"angle": 90, "orb": 7},
    "Sextile": {"angle": 60, "orb": 5},
    "Quincunx": {"angle": 150, "orb": 3},
    "Semisquare": {"angle": 45, "orb": 2},
    "Sesquisquare": {"angle": 135, "orb": 2},
}


def find_aspect(a: float, b: float) -> dict[str, object] | None:
    """Return the strongest matching aspect between two longitudes, or None."""
    # Angular separation in the 0..180 range.
    sep = abs(((a - b + 540) % 360) - 180)
    best: dict[str, object] | None = None
    for name, defn in ASPECTS.items():
        orb = abs(sep - defn["angle"])
        if orb <= defn["orb"] and (best is None or orb < best["orb"]):
            best = {"name": name, "orb": orb}
    return best


# ---------------------------------------------------------------------------
# Vedic / sidereal
# ---------------------------------------------------------------------------


def lahiri_ayanamsha_deg(dt: datetime) -> float:
    """Lahiri ayanamsha (degrees). Lahiri value at 1900.0 ~ 22.4606deg."""
    t = (_epoch_ms(dt) - _J1900_MS) / (86400 * 1000 * 365.25)
    arcseconds = 50.28792 * t  # seconds of arc since 1900
    return 22.4606 + arcseconds / 3600


def sidereal_longitude(tropical_lon: float, dt: datetime) -> float:
    """Sidereal (Vedic) longitude from tropical ecliptic longitude."""
    return norm360(tropical_lon - lahiri_ayanamsha_deg(dt))


NAKSHATRAS: tuple[str, ...] = (
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
)


def nakshatra(sidereal_lon: float) -> dict[str, object]:
    """Nakshatra (name, 1-based index, pada 1..4) for a sidereal longitude (deg)."""
    lon = norm360(sidereal_lon)
    # Each nakshatra spans 13°20' = 13.333... deg, divided into 4 padas of 3°20'.
    nak_size = 360 / 27
    idx = math.floor(lon / nak_size)
    pada = math.floor((lon - idx * nak_size) / (nak_size / 4)) + 1
    return {"name": NAKSHATRAS[idx], "index": idx + 1, "pada": pada}
