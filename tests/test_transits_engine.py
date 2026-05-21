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
