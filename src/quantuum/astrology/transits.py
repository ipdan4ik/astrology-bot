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
from quantuum.astrology.blueprint import BlueprintInput, parse_birth_instant
from quantuum.astrology.sections import ALL_PLANETS
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


def _aspect_offset(lon: float, n: float, theta_b: float) -> float:
    """Signed offset (deg, [-180,180)) of *lon* from natal *n* for branch *theta_b*."""
    return ((lon - n - theta_b + 180) % 360) - 180


def _is_retrograde(body: str, t: datetime) -> bool:
    l1 = ecliptic_longitude(body, t)
    l2 = ecliptic_longitude(body, t + timedelta(hours=6))
    return (((l2 - l1 + 540) % 360) - 180) < 0


def _bisect(body: str, n: float, theta_b: float, t0: datetime, t1: datetime) -> datetime:
    """Refine a confirmed sign-change bracket [t0, t1] to the exact crossing instant."""
    f0 = _aspect_offset(ecliptic_longitude(body, t0), n, theta_b)
    lo, hi = t0, t1
    for _ in range(BISECTION_ITERS):
        mid = lo + (hi - lo) / 2
        fm = _aspect_offset(ecliptic_longitude(body, mid), n, theta_b)
        if f0 * fm <= 0:
            hi = mid
        else:
            lo, f0 = mid, fm
    return lo + (hi - lo) / 2


def _branches(angle: float) -> tuple[float, ...]:
    """Aspect branches to scan: +/-angle, deduped for the symmetric 0 and 180."""
    if angle in (0.0, 180.0):
        return (angle,)
    return (angle, -angle)


def _find_hits(
    body: str,
    target: str,
    n: float,
    as_of: datetime,
    grid_times: list[datetime],
    grid_lons: list[float],
    window_end: datetime,
) -> list[TransitHit]:
    """All exact transits of *body* to natal *n* with as_of < exact_at <= window_end."""
    hits: list[TransitHit] = []
    for aspect, defn in TRANSIT_ASPECTS.items():
        for theta_b in _branches(defn["angle"]):
            for k in range(len(grid_times) - 1):
                f0 = _aspect_offset(grid_lons[k], n, theta_b)
                f1 = _aspect_offset(grid_lons[k + 1], n, theta_b)
                if f0 == 0.0:
                    exact = grid_times[k]
                elif f0 * f1 < 0 and abs(f1 - f0) < 180:
                    exact = _bisect(body, n, theta_b, grid_times[k], grid_times[k + 1])
                else:
                    continue
                if as_of < exact <= window_end:
                    hits.append(
                        TransitHit(
                            body=body,
                            target=target,
                            aspect=aspect,
                            exact_at=exact,
                            retrograde=_is_retrograde(body, exact),
                        )
                    )
    return hits


def _active_now(
    body: str,
    target: str,
    n: float,
    as_of: datetime,
    pair_hits: list[TransitHit],
) -> ActiveAspect | None:
    """Strongest aspect of *body* to natal *n* currently within orb, or None."""
    lon_now = ecliptic_longitude(body, as_of)
    sep = _sep180(lon_now, n)
    best: str | None = None
    best_orb = 0.0
    for aspect, defn in TRANSIT_ASPECTS.items():
        orb = abs(sep - defn["angle"])
        if orb <= defn["orb"] and (best is None or orb < best_orb):
            best, best_orb = aspect, orb
    if best is None:
        return None
    sep_later = _sep180(ecliptic_longitude(body, as_of + timedelta(hours=6)), n)
    orb_later = abs(sep_later - TRANSIT_ASPECTS[best]["angle"])
    applying = orb_later < best_orb
    futures = [h.exact_at for h in pair_hits if h.aspect == best and h.exact_at > as_of]
    exact_at = min(futures) if futures else None
    return ActiveAspect(
        body=body, target=target, aspect=best, orb=best_orb, applying=applying, exact_at=exact_at
    )


def compute_transits(
    inp: BlueprintInput, *, as_of: datetime, window_days: int = DEFAULT_WINDOW_DAYS
) -> TransitReport:
    window_days = clamp_window(window_days)
    window_end = as_of + timedelta(days=window_days)
    natal = compute_natal_targets(inp)

    sky = [
        SkyPosition(body=b, longitude=(p := planet_position(b, as_of)).longitude, retrograde=p.retrograde)
        for b in CURRENT_SKY_BODIES
    ]

    # Sample each forecast body's longitude on the daily grid once (reused across targets).
    n_steps = math.ceil(window_days * 24 / GRID_STEP_HOURS)
    grid_times = [as_of + timedelta(hours=GRID_STEP_HOURS * k) for k in range(n_steps + 2)]
    grid_lons = {b: [ecliptic_longitude(b, t) for t in grid_times] for b in TRANSIT_FORECAST_BODIES}

    all_hits: list[TransitHit] = []
    active: list[ActiveAspect] = []
    for b in TRANSIT_FORECAST_BODIES:
        for target in NATAL_TARGETS:
            n = natal[target]
            pair_hits = _find_hits(b, target, n, as_of, grid_times, grid_lons[b], window_end)
            all_hits.extend(pair_hits)
            act = _active_now(b, target, n, as_of, pair_hits)
            if act is not None:
                active.append(act)

    active.sort(key=lambda a: (not a.applying, a.orb))
    upcoming = sorted(
        (h for h in all_hits if h.exact_at > as_of), key=lambda h: h.exact_at
    )
    return TransitReport(
        as_of=as_of, window_days=window_days, sky=sky, active=active, upcoming=upcoming
    )


def render_transits_md(report: TransitReport) -> str:
    """Deterministic Markdown (3 tables) used to ground the LLM narration."""
    lines: list[str] = []

    lines.append("## Current sky")
    lines.append("")
    lines.append("| Body | Position | ℞ |")
    lines.append("| --- | --- | --- |")
    for s in report.sky:
        lines.append(
            f"| {s.body} | {fmt_deg(to_sign_degree(s.longitude))} | {'℞' if s.retrograde else ''} |"
        )
    lines.append("")

    lines.append("## Active transits now")
    lines.append("")
    if not report.active:
        lines.append("_No transits within orb right now._")
    else:
        lines.append("| Transit | Aspect | Natal | Orb | Phase | Exact |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for a in report.active:
            phase = "applying" if a.applying else "separating"
            exact = a.exact_at.strftime("%Y-%m-%d") if a.exact_at else "—"
            lines.append(
                f"| {a.body} | {a.aspect} | {a.target} | {to_fixed(a.orb, 2)}° | {phase} | {exact} |"
            )
    lines.append("")

    lines.append(f"## Upcoming exact transits (next {report.window_days} days)")
    lines.append("")
    if not report.upcoming:
        lines.append("_No exact transits in the window._")
    else:
        lines.append("| Date | Transit | Aspect | Natal | ℞ |")
        lines.append("| --- | --- | --- | --- | --- |")
        for h in report.upcoming:
            lines.append(
                f"| {h.exact_at.strftime('%Y-%m-%d')} | {h.body} | {h.aspect} | {h.target} | {'℞' if h.retrograde else ''} |"
            )
    lines.append("")

    return "\n".join(lines)


def render_daily_md(report: TransitReport, *, ahead_days: int = 3) -> str:
    """Compact daily grounding: active aspects now + exacts within *ahead_days*.

    Distinct from render_transits_md (the full 90-day 3-table report). Used to
    ground the short daily-horoscope narration. Deliberately omits the current-sky
    table and the retrograde marker to keep the grounding terse — the daily blurb
    leads with the active-now aspects, so that extra detail is not surfaced here.
    """
    cutoff = report.as_of + timedelta(days=ahead_days)
    lines: list[str] = []

    lines.append("## Active now")
    lines.append("")
    if not report.active:
        lines.append("_No active transits._")
    else:
        lines.append("| Transit | Aspect | Natal | Orb | Phase |")
        lines.append("| --- | --- | --- | --- | --- |")
        for a in report.active:
            phase = "applying" if a.applying else "separating"
            lines.append(f"| {a.body} | {a.aspect} | {a.target} | {to_fixed(a.orb, 2)}° | {phase} |")
    lines.append("")

    lines.append(f"## Exact within {ahead_days} days")
    lines.append("")
    imminent = [h for h in report.upcoming if h.exact_at <= cutoff]
    if not imminent:
        lines.append("_None._")
    else:
        lines.append("| Date | Transit | Aspect | Natal |")
        lines.append("| --- | --- | --- | --- |")
        for h in imminent:
            lines.append(f"| {h.exact_at.strftime('%Y-%m-%d')} | {h.body} | {h.aspect} | {h.target} |")
    lines.append("")

    return "\n".join(lines)
