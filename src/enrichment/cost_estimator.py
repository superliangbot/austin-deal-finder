"""Estimate total monthly cost for a rental listing.

Combines base rent with estimated utilities, renter's insurance,
pet rent, and parking to give an all-in monthly figure.
"""

import logging

logger = logging.getLogger(__name__)

# Utility estimates by bedroom count
_UTILITY_ESTIMATES = {
    0: 120,  # Studio
    1: 120,  # 1 BR: electric $60 + internet $50 + water $10
    2: 160,  # 2 BR
}
_UTILITY_DEFAULT = 200  # 3 BR+

_RENTERS_INSURANCE = 15
_PET_RENT = 35
_DOWNTOWN_PARKING = 50


def estimate_total_cost(listing: dict) -> float:
    """Estimate the all-in monthly cost for a listing.

    Components:
    - Base rent (from listing ``price``)
    - Estimated utilities based on bedroom count
    - Renter's insurance ($15/mo)
    - Pet rent ($35/mo) if pets are allowed and listing mentions a pet
    - Parking ($50/mo for downtown) unless the listing mentions parking included

    Returns the estimated total monthly cost as a float.
    """
    price = listing.get("price")
    if price is None:
        logger.warning("Listing has no price; cannot estimate total cost")
        return 0.0

    try:
        base_rent = float(price)
    except (TypeError, ValueError):
        logger.warning("Invalid price value: %s", price)
        return 0.0

    total = base_rent

    # --- Utilities ---
    bedrooms = listing.get("bedrooms")
    if bedrooms is not None:
        try:
            bedrooms = int(bedrooms)
        except (TypeError, ValueError):
            bedrooms = None

    if bedrooms is not None:
        utilities = _UTILITY_ESTIMATES.get(bedrooms, _UTILITY_DEFAULT)
    else:
        # Default to 1BR estimate when bedroom count is unknown
        utilities = _UTILITY_ESTIMATES[1]

    total += utilities
    logger.debug("Utilities estimate: $%d (bedrooms=%s)", utilities, bedrooms)

    # --- Renter's insurance ---
    total += _RENTERS_INSURANCE

    # --- Pet rent ---
    pets_allowed = listing.get("pets_allowed")
    # Check if the listing text mentions having a pet
    body_lower = str(listing.get("body", "")).lower()
    title_lower = str(listing.get("title", "")).lower()
    has_pet_mention = any(
        keyword in body_lower or keyword in title_lower
        for keyword in ("pet friendly", "pets ok", "pets allowed", "dog", "cat")
    )

    if pets_allowed is True or has_pet_mention:
        total += _PET_RENT
        logger.debug("Adding pet rent: $%d", _PET_RENT)

    # --- Parking ---
    parking_mentioned = any(
        keyword in body_lower or keyword in title_lower
        for keyword in ("parking included", "free parking", "parking spot", "garage included")
    )

    if parking_mentioned:
        logger.debug("Parking appears included; adding $0")
    else:
        total += _DOWNTOWN_PARKING
        logger.debug("No parking mentioned; adding downtown parking estimate: $%d", _DOWNTOWN_PARKING)

    logger.info(
        "Total cost estimate: $%.2f (rent=$%.2f, utilities=$%d, insurance=$%d)",
        total,
        base_rent,
        utilities,
        _RENTERS_INSURANCE,
    )
    return total
