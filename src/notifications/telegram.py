"""Telegram notification module for deal alerts."""

import logging
from datetime import datetime, timezone

import httpx

from src.config import settings
from src.scoring.deal_scorer import calculate_deal_score, classify_deal

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Classification emoji mapping
CLASSIFICATION_EMOJIS = {
    "STEAL": "\U0001f525",       # fire
    "GOOD_DEAL": "\u2705",      # check mark
    "AVERAGE": "\u27a1\ufe0f",  # right arrow
    "OVERPRICED": "\u274c",     # x mark
}


def _get(listing, key, default=None):
    """Get attribute from ORM object or dict."""
    if isinstance(listing, dict):
        return listing.get(key, default)
    return getattr(listing, key, default)


def _format_alert(listing) -> str:
    """Format a listing into a Telegram alert message using HTML parse mode.

    Follows the notification spec format from BUILD_SPEC.md.
    """
    # Get deal score and classification
    deal_score = _get(listing, "deal_score")
    if deal_score is None:
        deal_score = calculate_deal_score(listing)

    classification = _get(listing, "deal_classification")
    if not classification:
        classification = classify_deal(deal_score)

    emoji = CLASSIFICATION_EMOJIS.get(classification, "")
    class_label = classification.replace("_", " ")

    # Header
    lines = [
        f"{emoji} <b>{class_label} ALERT</b> \u2014 Deal Score: {deal_score}/100",
        "",
    ]

    # Title and price
    title = _get(listing, "title") or "Untitled Listing"
    price = _get(listing, "price")
    price_str = f"${float(price):,.0f}/mo" if price else "Price unknown"
    lines.append(f"\U0001f4cd {title} \u2014 {price_str}")

    # Type, sqft, furnished
    listing_type = _get(listing, "listing_type") or "Unknown type"
    sqft = _get(listing, "sqft")
    furnished = _get(listing, "furnished")
    details = [listing_type]
    if sqft:
        details.append(f"{sqft} sqft")
    if furnished:
        details.append("Furnished")
    lines.append(f"\U0001f3e0 {' | '.join(details)}")

    # Distance and walk time
    distance = _get(listing, "distance_miles")
    walk_min = _get(listing, "walk_minutes")
    if distance is not None:
        dist_str = f"{float(distance):.1f} miles from Congress Ave"
        if walk_min:
            dist_str += f" ({walk_min} min walk)"
        lines.append(f"\U0001f4cf {dist_str}")

    # Estimated all-in cost
    estimated_total = _get(listing, "estimated_total")
    if estimated_total:
        lines.append(f"\U0001f4b0 Est. all-in: ${float(estimated_total):,.0f}/mo")

    # Incentives
    incentives = _get(listing, "incentives")
    if incentives:
        incentive_text = ", ".join(incentives)
        lines.append(f"\U0001f3f7\ufe0f Incentives: {incentive_text}")

    # Available date
    available_date = _get(listing, "available_date")
    if available_date:
        if isinstance(available_date, str):
            lines.append(f"\U0001f4c5 Available: {available_date}")
        else:
            lines.append(f"\U0001f4c5 Available: {available_date.strftime('%B %d')}")

    # Urgency
    urgency = _get(listing, "urgency_score")
    if urgency:
        urgency = int(urgency)
        if urgency >= 8:
            urgency_label = "HIGH"
        elif urgency >= 5:
            urgency_label = "MEDIUM"
        else:
            urgency_label = "LOW"
        lines.append(f"\u26a1 Urgency: {urgency_label} ({urgency}/10)")

    lines.append("")

    # Summary
    summary = _get(listing, "summary")
    if summary:
        lines.append(f"\U0001f4dd <i>{summary}</i>")
        lines.append("")

    # Outreach suggestion
    outreach = _get(listing, "outreach_suggestion")
    if outreach:
        lines.append(f'\U0001f4ac Suggested outreach: "{outreach}"')
        lines.append("")

    # Source link
    source_url = _get(listing, "source_url")
    source = _get(listing, "source") or "Unknown"
    if source_url:
        lines.append(f'\U0001f517 <a href="{source_url}">View listing</a>')

    # Source and posting age
    first_seen = _get(listing, "first_seen_at")
    age_str = ""
    if first_seen:
        if isinstance(first_seen, str):
            first_seen = datetime.fromisoformat(first_seen)
        now = datetime.now(timezone.utc)
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        age_hours = (now - first_seen).total_seconds() / 3600
        if age_hours < 1:
            age_str = f" | Posted: {int(age_hours * 60)} minutes ago"
        elif age_hours < 24:
            age_str = f" | Posted: {int(age_hours)} hours ago"
        else:
            age_str = f" | Posted: {int(age_hours / 24)} days ago"

    lines.append(f"Source: {source.capitalize()}{age_str}")

    return "\n".join(lines)


async def send_alert(listing) -> bool:
    """Format and send a deal notification via Telegram.

    Args:
        listing: A Listing ORM object or dict with listing data.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        logger.error("Telegram bot token or chat ID not configured. Skipping alert.")
        return False

    message = _format_alert(listing)
    url = TELEGRAM_API_URL.format(token=token)

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            if result.get("ok"):
                title = _get(listing, "title") or "Unknown"
                logger.info("Telegram alert sent for listing: %s", title)
                return True
            else:
                logger.error(
                    "Telegram API returned error: %s",
                    result.get("description", "Unknown error"),
                )
                return False

    except httpx.HTTPStatusError as exc:
        logger.error(
            "HTTP error sending Telegram alert: %s %s",
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error("Network error sending Telegram alert: %s", exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error sending Telegram alert: %s", exc)
        return False


async def send_batch_alerts(listings) -> int:
    """Send Telegram alerts for multiple listings.

    Args:
        listings: Iterable of Listing ORM objects or dicts.

    Returns:
        Number of successfully sent alerts.
    """
    sent_count = 0

    for listing in listings:
        try:
            success = await send_alert(listing)
            if success:
                sent_count += 1
        except Exception as exc:
            title = _get(listing, "title") or "Unknown"
            logger.error("Failed to send alert for listing '%s': %s", title, exc)

    logger.info("Batch alerts complete: %d/%d sent successfully", sent_count, len(listings))
    return sent_count
