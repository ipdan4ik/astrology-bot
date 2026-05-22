from dataclasses import dataclass

import httpx
from timezonefinder import TimezoneFinder

from quantuum.logging_setup import get_logger
from quantuum.settings import get_settings

logger = get_logger("geocoding")

_tf = TimezoneFinder()


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lon: float
    display_name: str


_TIMEOUT = httpx.Timeout(10.0)


def _headers() -> dict[str, str]:
    return {"User-Agent": get_settings().geocoder_user_agent}


async def geocode(query: str, *, limit: int = 1) -> list[GeoResult]:
    """Forward-geocode free text via a Nominatim-compatible endpoint.

    Returns [] on empty query or any network/HTTP error (caller re-prompts).
    """
    q = (query or "").strip()
    if not q:
        return []
    url = f"{get_settings().geocoder_url}/search"
    params = {"q": q, "format": "jsonv2", "limit": limit, "accept-language": "ru"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("geocode_failed", query=q)
        return []
    return [
        GeoResult(float(o["lat"]), float(o["lon"]), o["display_name"])
        for o in data
        if "lat" in o and "lon" in o
    ]


async def reverse(lat: float, lon: float) -> GeoResult | None:
    """Reverse-geocode coordinates to a display name. None on failure/no result."""
    url = f"{get_settings().geocoder_url}/reverse"
    params = {"lat": lat, "lon": lon, "format": "jsonv2", "accept-language": "ru"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("reverse_failed", lat=lat, lon=lon)
        return None
    if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
        return None
    return GeoResult(float(data["lat"]), float(data["lon"]), data.get("display_name", ""))


def coords_to_timezone(lat: float, lon: float) -> str:
    """IANA timezone for coordinates (offline, deterministic).

    Falls back to the closest zone for edge/coastal points; "UTC" only as a last resort.
    """
    tz = _tf.timezone_at(lat=lat, lng=lon)
    if tz is None:
        tz = _tf.closest_timezone_at(lat=lat, lng=lon)
    return tz or "UTC"
