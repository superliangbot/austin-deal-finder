"""Geocoding and distance calculation for listings.

Uses OpenStreetMap Nominatim for geocoding addresses to coordinates,
OSRM for driving time, and walking speed estimation for walk times.
All free, no API keys needed.
"""

import logging
import math
import time

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Office location: 600 N Congress Ave, Austin, TX 78701
OFFICE_LAT = 30.2694558
OFFICE_LON = -97.7422904

# Walking speed in mph (average human)
WALK_SPEED_MPH = 3.0

# Rate limiting for Nominatim (max 1 req/sec per their policy)
_last_nominatim_call = 0.0

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_ROUTE_URL = "http://router.project-osrm.org/route/v1/driving"

HEADERS = {"User-Agent": "AustinDealFinder/1.0 (housing search)"}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in miles.

    Args:
        lat1, lon1: First point coordinates.
        lat2, lon2: Second point coordinates.

    Returns:
        Distance in miles.
    """
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode an address string to (lat, lon) using Nominatim.

    Respects Nominatim's 1 request/second rate limit.

    Args:
        address: Address or location string.

    Returns:
        (latitude, longitude) tuple, or None if geocoding fails.
    """
    global _last_nominatim_call

    if not address or len(address.strip()) < 3:
        return None

    # Rate limit: 1 req/sec for Nominatim
    elapsed = time.time() - _last_nominatim_call
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    # Append Austin, TX if not present to improve results
    query = address.strip()
    if "austin" not in query.lower() and "tx" not in query.lower():
        query = f"{query}, Austin, TX"

    try:
        _last_nominatim_call = time.time()
        response = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()

        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return (lat, lon)

    except Exception:
        logger.debug("Geocoding failed for: %s", address)

    return None


def get_driving_time(lat: float, lon: float) -> tuple[float, float] | None:
    """Get driving distance and time from a point to the office using OSRM.

    Args:
        lat: Latitude of the listing.
        lon: Longitude of the listing.

    Returns:
        (distance_miles, duration_minutes) tuple, or None on error.
    """
    try:
        url = f"{OSRM_ROUTE_URL}/{OFFICE_LON},{OFFICE_LAT};{lon},{lat}"
        response = httpx.get(
            url,
            params={"overview": "false"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("routes"):
            route = data["routes"][0]
            dist_miles = route["distance"] / 1609.34
            duration_min = route["duration"] / 60
            return (dist_miles, duration_min)

    except Exception:
        logger.debug("OSRM routing failed for (%s, %s)", lat, lon)

    return None


def estimate_walk_time(distance_miles: float) -> float:
    """Estimate walking time in minutes from road distance.

    Args:
        distance_miles: Road distance in miles.

    Returns:
        Estimated walking time in minutes.
    """
    return (distance_miles / WALK_SPEED_MPH) * 60


def enrich_listing_with_distance(listing: dict) -> dict:
    """Add distance and travel time data to a listing.

    Tries to geocode the address, then calculates:
    - distance_miles (haversine)
    - walk_minutes (estimated from road distance)
    - drive_minutes (from OSRM)
    - latitude/longitude

    Args:
        listing: Listing dict to enrich.

    Returns:
        The same listing dict with distance fields added.
    """
    address = listing.get("address") or ""
    title = listing.get("title") or ""

    coords = None

    # Try geocoding the address
    if address:
        coords = geocode_address(address)

    # Fallback: try geocoding from title (sometimes has location info)
    if not coords and title:
        # Extract location hints from title
        for hint in _extract_location_hints(title):
            coords = geocode_address(hint)
            if coords:
                break

    if coords:
        lat, lon = coords
        listing["latitude"] = lat
        listing["longitude"] = lon

        # Haversine distance (straight line)
        listing["distance_miles"] = round(haversine_distance(OFFICE_LAT, OFFICE_LON, lat, lon), 2)

        # OSRM driving route
        drive_result = get_driving_time(lat, lon)
        if drive_result:
            road_dist, drive_min = drive_result
            listing["drive_minutes"] = round(drive_min, 0)
            listing["road_distance_miles"] = round(road_dist, 2)
            listing["walk_minutes"] = round(estimate_walk_time(road_dist), 0)
        else:
            # Fallback: estimate from haversine (multiply by 1.3 for road factor)
            est_road = listing["distance_miles"] * 1.3
            listing["walk_minutes"] = round(estimate_walk_time(est_road), 0)
            listing["drive_minutes"] = round(est_road / 30 * 60, 0)  # assume 30mph avg

    return listing


def _extract_location_hints(text: str) -> list[str]:
    """Extract potential location strings from text.

    Looks for neighborhood names, street names, and zip codes.
    """
    hints = []
    text_lower = text.lower()

    # Known Austin neighborhoods
    neighborhoods = [
        "downtown", "west campus", "east austin", "south congress", "soco",
        "rainey", "zilker", "barton hills", "travis heights", "south lamar",
        "north loop", "hyde park", "mueller", "riverside", "bouldin",
        "clarksville", "old west austin", "rosedale", "crestview",
        "south austin", "north austin", "east side", "78701", "78702",
        "78703", "78704", "78705",
    ]

    for n in neighborhoods:
        if n in text_lower:
            hints.append(f"{n}, Austin, TX")

    return hints


def is_within_walk(listing: dict, max_minutes: int = 30) -> bool:
    """Check if listing is within walking distance.

    Args:
        listing: Enriched listing dict.
        max_minutes: Maximum walk time in minutes.

    Returns:
        True if walkable within the time limit.
    """
    walk_min = listing.get("walk_minutes")
    if walk_min is not None:
        return walk_min <= max_minutes
    return False


def is_within_drive(listing: dict, max_minutes: int = 20) -> bool:
    """Check if listing is within driving distance.

    Args:
        listing: Enriched listing dict.
        max_minutes: Maximum drive time in minutes.

    Returns:
        True if driveable within the time limit.
    """
    drive_min = listing.get("drive_minutes")
    if drive_min is not None:
        return drive_min <= max_minutes
    return False
