"""Geocoding and distance calculation utilities.

Uses OpenStreetMap Nominatim for geocoding and the haversine formula
for computing distances between coordinates.
"""

import logging
import math

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Earth radius in miles
_EARTH_RADIUS_MILES = 3959


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in miles between two points on Earth.

    Uses the haversine formula with Earth radius of 3959 miles.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return _EARTH_RADIUS_MILES * c


def estimate_walk_minutes(distance_miles: float) -> int:
    """Estimate walking time in minutes for a given distance in miles.

    Uses a rough factor of 20 minutes per mile (about 3 mph walking speed).
    """
    return round(distance_miles * 20)


def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode an address string to (latitude, longitude) using Nominatim.

    Returns ``None`` when the address cannot be resolved.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
    }
    headers = {
        "User-Agent": "AustinDealFinder/1.0 (housing search tool)",
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            results = response.json()

        if not results:
            logger.warning("No geocoding results for address: %s", address)
            return None

        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
        logger.info("Geocoded '%s' to (%f, %f)", address, lat, lon)
        return (lat, lon)

    except httpx.HTTPError as exc:
        logger.error("HTTP error during geocoding for '%s': %s", address, exc)
        return None
    except (KeyError, IndexError, ValueError) as exc:
        logger.error("Failed to parse geocoding response for '%s': %s", address, exc)
        return None


def calculate_distance_from_target(lat: float, lon: float) -> float:
    """Return the distance in miles from the configured target location.

    The default target is 600 Congress Ave, Austin, TX (30.2672, -97.7431).
    """
    return haversine_distance(settings.target_lat, settings.target_lon, lat, lon)


def enrich_listing_location(listing_data: dict) -> dict:
    """Enrich a listing dict with location-derived fields.

    If the listing already has ``lat`` and ``lon`` keys they are reused;
    otherwise the ``address`` field is geocoded via Nominatim.

    Added / updated keys:
    - ``lat``, ``lon`` (floats or None)
    - ``distance_miles`` (float or None)
    - ``walk_minutes`` (int or None)
    """
    data = dict(listing_data)  # shallow copy to avoid mutating the original

    lat = data.get("lat")
    lon = data.get("lon")

    # Attempt geocoding when coordinates are missing
    if lat is None or lon is None:
        address = data.get("address")
        if address:
            coords = geocode_address(address)
            if coords is not None:
                lat, lon = coords
                data["lat"] = lat
                data["lon"] = lon
            else:
                logger.warning(
                    "Could not geocode listing address: %s", address
                )
                data["distance_miles"] = None
                data["walk_minutes"] = None
                return data
        else:
            logger.warning("Listing has no address and no coordinates; skipping location enrichment")
            data["distance_miles"] = None
            data["walk_minutes"] = None
            return data

    distance = calculate_distance_from_target(lat, lon)
    data["distance_miles"] = round(distance, 2)
    data["walk_minutes"] = estimate_walk_minutes(distance)

    logger.info(
        "Location enrichment complete: %.2f miles, ~%d min walk",
        data["distance_miles"],
        data["walk_minutes"],
    )
    return data
