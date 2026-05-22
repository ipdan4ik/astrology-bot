def test_coords_to_timezone_known_cities():
    from quantuum.geocoding import coords_to_timezone

    assert coords_to_timezone(55.7558, 37.6173) == "Europe/Moscow"
    assert coords_to_timezone(52.52, 13.405) == "Europe/Berlin"


def test_coords_to_timezone_returns_str_for_ocean_like_point():
    # A point far at sea still resolves to some IANA zone (closest), never crashes.
    from quantuum.geocoding import coords_to_timezone

    tz = coords_to_timezone(0.0, -160.0)
    assert isinstance(tz, str) and tz
