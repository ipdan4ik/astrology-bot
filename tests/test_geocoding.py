import httpx


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, data=None, error=None):
        self._data = data
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if self._error is not None:
            raise self._error
        return _FakeResp(self._data)


async def test_geocode_parses_results(monkeypatch):
    from quantuum import geocoding

    payload = [
        {"lat": "55.7558", "lon": "37.6173", "display_name": "Moscow, Russia"},
        {"lat": "46.35", "lon": "-94.0", "display_name": "Moscow, Latah County, Idaho, USA"},
    ]
    monkeypatch.setattr(geocoding.httpx, "AsyncClient", lambda **kw: _FakeClient(data=payload))

    results = await geocoding.geocode("Moscow", limit=2)
    assert results[0] == geocoding.GeoResult(55.7558, 37.6173, "Moscow, Russia")
    assert len(results) == 2


async def test_geocode_empty_query_returns_empty():
    from quantuum import geocoding

    assert await geocoding.geocode("   ") == []


async def test_geocode_network_error_returns_empty(monkeypatch):
    from quantuum import geocoding

    monkeypatch.setattr(
        geocoding.httpx,
        "AsyncClient",
        lambda **kw: _FakeClient(error=httpx.ConnectError("boom")),
    )
    assert await geocoding.geocode("Moscow") == []


async def test_reverse_parses_or_none(monkeypatch):
    from quantuum import geocoding

    monkeypatch.setattr(
        geocoding.httpx,
        "AsyncClient",
        lambda **kw: _FakeClient(data={"lat": "55.75", "lon": "37.62", "display_name": "Moscow"}),
    )
    got = await geocoding.reverse(55.75, 37.62)
    assert got == geocoding.GeoResult(55.75, 37.62, "Moscow")

    monkeypatch.setattr(
        geocoding.httpx, "AsyncClient", lambda **kw: _FakeClient(data={"error": "Unable to geocode"})
    )
    assert await geocoding.reverse(0.0, 0.0) is None


def test_coords_to_timezone_known_cities():
    from quantuum.geocoding import coords_to_timezone

    assert coords_to_timezone(55.7558, 37.6173) == "Europe/Moscow"
    assert coords_to_timezone(52.52, 13.405) == "Europe/Berlin"


def test_coords_to_timezone_returns_str_for_ocean_like_point():
    # A point far at sea still resolves to some IANA zone (closest), never crashes.
    from quantuum.geocoding import coords_to_timezone

    tz = coords_to_timezone(0.0, -160.0)
    assert isinstance(tz, str) and tz
