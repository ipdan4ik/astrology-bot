from dataclasses import dataclass

from timezonefinder import TimezoneFinder

from quantuum.logging_setup import get_logger

logger = get_logger("geocoding")

_tf = TimezoneFinder()


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lon: float
    display_name: str


def coords_to_timezone(lat: float, lon: float) -> str:
    """IANA timezone for coordinates (offline, deterministic).

    Falls back to the closest zone for edge/coastal points; "UTC" only as a last resort.
    """
    tz = _tf.timezone_at(lat=lat, lng=lon)
    if tz is None:
        tz = _tf.closest_timezone_at(lat=lat, lng=lon)
    return tz or "UTC"
