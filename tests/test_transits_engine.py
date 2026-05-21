from datetime import datetime, timedelta, timezone

from quantuum.astrology.blueprint import BlueprintInput
from quantuum.astrology.transits import (
    DEFAULT_WINDOW_DAYS,
    MAX_WINDOW_DAYS,
    MIN_WINDOW_DAYS,
    NATAL_TARGETS,
    clamp_window,
    compute_natal_targets,
)


def _inp() -> BlueprintInput:
    return BlueprintInput(
        full_name="Anna", birth_date="1990-06-15", birth_time="14:30",
        birth_place="Moscow", latitude=55.7558, longitude=37.6176,
        timezone="Europe/Moscow",
    )


def test_clamp_window_defaults_and_bounds():
    assert clamp_window(None) == DEFAULT_WINDOW_DAYS
    assert clamp_window("nonsense") == DEFAULT_WINDOW_DAYS
    assert clamp_window(1) == MIN_WINDOW_DAYS
    assert clamp_window(9999) == MAX_WINDOW_DAYS
    assert clamp_window(30) == 30
    assert clamp_window("45") == 45


def test_compute_natal_targets_has_all_points():
    targets = compute_natal_targets(_inp())
    assert set(targets) == set(NATAL_TARGETS)
    for v in targets.values():
        assert 0.0 <= v < 360.0


def test_compute_natal_targets_matches_engine():
    # Asc must match astro.ascendant_longitude for the same birth instant.
    from quantuum.astrology.astro import ascendant_longitude
    from quantuum.astrology.blueprint import parse_birth_instant

    inp = _inp()
    birth = parse_birth_instant(inp)
    targets = compute_natal_targets(inp)
    assert abs(targets["Asc"] - ascendant_longitude(birth, inp.latitude, inp.longitude)) < 1e-9


def test_find_hits_forward_single(monkeypatch):
    from quantuum.astrology import transits as T

    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def fake_lon(body, t):
        days = (t - as_of).total_seconds() / 86400
        return (1.0 * days) % 360  # 1 deg/day from 0

    monkeypatch.setattr(T, "ecliptic_longitude", fake_lon)
    grid_times = [as_of + timedelta(days=k) for k in range(0, 31)]
    grid_lons = [fake_lon("X", t) for t in grid_times]

    hits = T._find_hits("X", "Sun", 10.0, as_of, grid_times, grid_lons, as_of + timedelta(days=30))
    conj = [h for h in hits if h.aspect == "Conjunction"]
    assert len(conj) == 1
    # Conjunction (lon == 10) exact at ~day 10.
    assert abs((conj[0].exact_at - (as_of + timedelta(days=10))).total_seconds()) < 3600
    assert conj[0].body == "X" and conj[0].target == "Sun"


def test_find_hits_retrograde_triple(monkeypatch):
    from quantuum.astrology import transits as T

    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def fake_lon(body, t):
        d = (t - as_of).total_seconds() / 86400
        if d <= 20:
            return 0.6 * d            # 0 -> 12, crosses 10 going up (~16.7d)
        if d <= 40:
            return 12 - 0.6 * (d - 20)  # 12 -> 0, crosses 10 going down (~23.3d)
        return 0.6 * (d - 40)         # 0 -> .. crosses 10 going up again (~56.7d)

    monkeypatch.setattr(T, "ecliptic_longitude", fake_lon)
    grid_times = [as_of + timedelta(days=k) for k in range(0, 61)]
    grid_lons = [fake_lon("X", t) for t in grid_times]

    hits = T._find_hits("X", "Sun", 10.0, as_of, grid_times, grid_lons, as_of + timedelta(days=60))
    conj = [h for h in hits if h.aspect == "Conjunction"]
    assert len(conj) == 3  # triple pass over the natal point
    # The middle pass is retrograde (longitude decreasing).
    assert any(h.retrograde for h in conj)


def test_find_hits_bisection_accuracy(monkeypatch):
    from quantuum.astrology import transits as T

    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def fake_lon(body, t):
        days = (t - as_of).total_seconds() / 86400
        return (2.0 * days) % 360

    monkeypatch.setattr(T, "ecliptic_longitude", fake_lon)
    grid_times = [as_of + timedelta(days=k) for k in range(0, 61)]
    grid_lons = [fake_lon("X", t) for t in grid_times]

    # natal 5 -> Square exact when lon == 95 (day 47.5, BETWEEN grid points 47 and 48,
    # so this exercises the bisection path, not the exact-grid-point shortcut).
    hits = T._find_hits("X", "Sun", 5.0, as_of, grid_times, grid_lons, as_of + timedelta(days=60))
    sq = [h for h in hits if h.aspect == "Square"]
    assert len(sq) == 1
    assert abs((sq[0].exact_at - (as_of + timedelta(days=47.5))).total_seconds()) < 600
