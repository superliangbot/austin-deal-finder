"""Deal scoring engine — scores listings 0-100."""

from datetime import datetime, timezone
import logging

from src.config import settings

logger = logging.getLogger(__name__)


def calculate_deal_score(listing) -> int:
    """Score 0-100 based on multiple factors.

    `listing` can be a Listing ORM object or a dict with the same keys.
    """
    score = 50  # baseline

    # Helper to get attribute from object or dict
    def get(key, default=None):
        if isinstance(listing, dict):
            return listing.get(key, default)
        return getattr(listing, key, default)

    # Price factor (30 points max)
    price = get("price")
    avg_market = settings.avg_market_rent
    if price:
        price = float(price)
        price_ratio = price / avg_market
        if price_ratio < 0.7:
            score += 30
        elif price_ratio < 0.85:
            score += 20
        elif price_ratio < 1.0:
            score += 10
        elif price_ratio > 1.2:
            score -= 15

    # Distance factor (20 points max)
    distance = get("distance_miles")
    if distance:
        distance = float(distance)
        if distance < 0.5:
            score += 20
        elif distance < 1.0:
            score += 15
        elif distance < 1.5:
            score += 10
        elif distance < 2.0:
            score += 5
        else:
            score -= 10

    # Urgency factor (10 points max)
    urgency = get("urgency_score")
    if urgency:
        score += min(int(urgency), 10)

    # Incentives (10 points max)
    incentives = get("incentives")
    if incentives:
        score += min(len(incentives) * 5, 10)

    # Freshness (10 points max)
    first_seen = get("first_seen_at")
    if first_seen:
        if isinstance(first_seen, str):
            first_seen = datetime.fromisoformat(first_seen)
        now = datetime.now(timezone.utc)
        if first_seen.tzinfo is None:
            from datetime import timezone as tz
            first_seen = first_seen.replace(tzinfo=tz.utc)
        age_hours = (now - first_seen).total_seconds() / 3600
        if age_hours < 2:
            score += 10
        elif age_hours < 12:
            score += 7
        elif age_hours < 24:
            score += 4

    # Furnished bonus (5 points)
    if get("furnished"):
        score += 5

    return max(0, min(100, score))


def classify_deal(score: int) -> str:
    """Classify deal based on score."""
    if score >= 80:
        return "STEAL"
    elif score >= 65:
        return "GOOD_DEAL"
    elif score >= 40:
        return "AVERAGE"
    else:
        return "OVERPRICED"
