"""Manual input handler for listings that cannot be scraped automatically.

Provides methods to manually add listings (e.g., from Facebook groups)
and to parse pasted listing text into structured data.
"""

import hashlib
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Regex for price extraction
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")

# Regex for bedroom count
BEDS_PATTERN = re.compile(r"(\d+)\s*(?:bed|br|bedroom|bd)", re.IGNORECASE)

# Regex for bathroom count
BATHS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath|ba|bathroom)", re.IGNORECASE)

# Regex for square footage
SQFT_PATTERN = re.compile(r"([\d,]+)\s*(?:sq\s*ft|sqft|sf)", re.IGNORECASE)


def _generate_source_id(content: str) -> str:
    """Generate a deterministic source ID from content by hashing.

    Args:
        content: Text content to hash (typically title + description).

    Returns:
        Hex string of the first 16 characters of the SHA-256 hash.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _normalize_manual_listing(
    source_id: str,
    source_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    price: float | None = None,
    bedrooms: int | None = None,
    bathrooms: float | None = None,
    sqft: int | None = None,
    address: str | None = None,
    listing_type: str | None = None,
    furnished: bool | None = None,
    pets_allowed: bool | None = None,
    available_date: str | None = None,
    contact_info: str | None = None,
    images: list[str] | None = None,
    raw_data: dict | None = None,
) -> dict:
    """Create a normalized listing dict for a manual entry.

    Args:
        source_id: Unique ID for this manual listing.
        source_url: URL to the original listing if available.
        title: Listing title.
        description: Full description text.
        price: Monthly rent.
        bedrooms: Number of bedrooms.
        bathrooms: Number of bathrooms.
        sqft: Square footage.
        address: Street address or location.
        listing_type: Type of listing.
        furnished: Whether furnished.
        pets_allowed: Whether pets are allowed.
        available_date: Available date as ISO string.
        contact_info: Contact information.
        images: List of image URLs.
        raw_data: Original raw data.

    Returns:
        Normalized listing dictionary.
    """
    return {
        "source": "manual",
        "source_id": source_id,
        "source_url": source_url,
        "title": title,
        "description": description,
        "price": price,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "sqft": sqft,
        "address": address,
        "listing_type": listing_type,
        "furnished": furnished,
        "pets_allowed": pets_allowed,
        "available_date": available_date,
        "contact_info": contact_info,
        "images": images or [],
        "raw_data": raw_data or {},
    }


class ManualInput:
    """Handler for manually added listings.

    NOT a web scraper -- provides methods for users to add listings
    manually (e.g., from Facebook groups that cannot be scraped)
    and to parse pasted text into structured listing data.
    """

    def add_listing(self, data: dict) -> dict:
        """Add a listing from manually provided data.

        Validates required fields and normalizes the data
        into the standard listing format.

        Args:
            data: Dictionary with listing data. Required fields:
                  - title (str)
                  - price (float/int) OR description (str)
                  - source_url (str) OR description (str)

        Returns:
            Normalized listing dictionary.

        Raises:
            ValueError: If required fields are missing.
        """
        title = data.get("title")
        price = data.get("price")
        source_url = data.get("source_url")
        description = data.get("description")

        # Validate required fields
        if not title:
            raise ValueError("Missing required field: 'title'")

        if price is None and not description:
            raise ValueError(
                "At least one of 'price' or 'description' is required"
            )

        if not source_url and not description:
            raise ValueError(
                "At least one of 'source_url' or 'description' is required"
            )

        # Convert price to float if provided
        if price is not None:
            try:
                price = float(price)
            except (TypeError, ValueError):
                logger.warning("Invalid price value: %s, setting to None", price)
                price = None

        # Generate a source ID from the content
        content_for_hash = f"{title}|{description or ''}|{source_url or ''}"
        source_id = _generate_source_id(content_for_hash)

        # Extract any additional fields from data
        bedrooms = data.get("bedrooms")
        if bedrooms is not None:
            try:
                bedrooms = int(bedrooms)
            except (TypeError, ValueError):
                bedrooms = None

        bathrooms = data.get("bathrooms")
        if bathrooms is not None:
            try:
                bathrooms = float(bathrooms)
            except (TypeError, ValueError):
                bathrooms = None

        sqft = data.get("sqft")
        if sqft is not None:
            try:
                sqft = int(sqft)
            except (TypeError, ValueError):
                sqft = None

        listing = _normalize_manual_listing(
            source_id=source_id,
            source_url=source_url,
            title=title,
            description=description,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            address=data.get("address"),
            listing_type=data.get("listing_type"),
            furnished=data.get("furnished"),
            pets_allowed=data.get("pets_allowed"),
            available_date=data.get("available_date"),
            contact_info=data.get("contact_info"),
            images=data.get("images", []),
            raw_data={
                "input_method": "manual",
                "added_at": datetime.utcnow().isoformat(),
                "original_data": data,
            },
        )

        logger.info(
            "Manual listing added: %s (source_id=%s, price=%s)",
            title, source_id, price,
        )
        return listing

    def from_facebook_paste(self, text: str) -> dict:
        """Parse pasted Facebook listing text into a structured listing.

        Attempts to extract price, bedrooms, bathrooms, sqft, and other
        details from free-form text that was copied from a Facebook
        housing group post.

        Args:
            text: Raw text pasted from a Facebook listing post.

        Returns:
            Normalized listing dictionary.

        Raises:
            ValueError: If the text is empty or cannot be parsed into
                        a meaningful listing.
        """
        if not text or not text.strip():
            raise ValueError("Empty text provided")

        text = text.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if not lines:
            raise ValueError("No meaningful content in pasted text")

        # First non-empty line is typically the title
        title = lines[0]

        # Join remaining lines as description
        description = "\n".join(lines[1:]) if len(lines) > 1 else text

        # Extract price
        price = None
        price_match = PRICE_PATTERN.search(text)
        if price_match:
            price_str = price_match.group(0).replace("$", "").replace(",", "").replace("/mo", "")
            try:
                price = float(price_str)
            except ValueError:
                pass

        # Extract bedrooms
        bedrooms = None
        beds_match = BEDS_PATTERN.search(text)
        if beds_match:
            try:
                bedrooms = int(beds_match.group(1))
            except ValueError:
                pass
        # Check for "studio"
        if bedrooms is None and re.search(r"\bstudio\b", text, re.IGNORECASE):
            bedrooms = 0

        # Extract bathrooms
        bathrooms = None
        baths_match = BATHS_PATTERN.search(text)
        if baths_match:
            try:
                bathrooms = float(baths_match.group(1))
            except ValueError:
                pass

        # Extract sqft
        sqft = None
        sqft_match = SQFT_PATTERN.search(text)
        if sqft_match:
            try:
                sqft = int(sqft_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Try to detect listing type
        listing_type = None
        text_lower = text.lower()
        if "sublease" in text_lower or "sublet" in text_lower:
            listing_type = "sublease"
        elif "lease takeover" in text_lower or "take over" in text_lower:
            listing_type = "lease_takeover"
        elif "roommate" in text_lower or "room for rent" in text_lower:
            listing_type = "roommate"
        elif "apartment" in text_lower or "apt" in text_lower:
            listing_type = "apartment"

        # Try to detect furnished status
        furnished = None
        if re.search(r"\bfurnished\b", text, re.IGNORECASE):
            furnished = True
        elif re.search(r"\bunfurnished\b", text, re.IGNORECASE):
            furnished = False

        # Try to detect pet policy
        pets_allowed = None
        if re.search(r"\bpets?\s*(ok|allowed|friendly|welcome)\b", text, re.IGNORECASE):
            pets_allowed = True
        elif re.search(r"\bno\s*pets?\b", text, re.IGNORECASE):
            pets_allowed = False

        # Try to extract a URL from the text
        source_url = None
        url_match = re.search(r"https?://\S+", text)
        if url_match:
            source_url = url_match.group(0).rstrip(".,;!?)")

        # Try to extract contact info
        contact_info = None
        # Look for phone numbers
        phone_match = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
        if phone_match:
            contact_info = phone_match.group(0)
        # Look for email
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
        if email_match:
            email = email_match.group(0)
            contact_info = f"{contact_info}, {email}" if contact_info else email

        # Try to extract address (look for common Austin patterns)
        address = None
        # Match patterns like "123 Main St" or "123 E 6th Street"
        addr_match = re.search(
            r"\d+\s+(?:[NSEW]\.?\s+)?(?:\w+\s+){1,3}(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|Way|Ct|Court|Pl|Place)\.?",
            text,
            re.IGNORECASE,
        )
        if addr_match:
            address = addr_match.group(0)

        # Generate source ID from content
        source_id = _generate_source_id(text)

        listing = _normalize_manual_listing(
            source_id=source_id,
            source_url=source_url,
            title=title,
            description=description,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            address=address,
            listing_type=listing_type,
            furnished=furnished,
            pets_allowed=pets_allowed,
            contact_info=contact_info,
            raw_data={
                "input_method": "facebook_paste",
                "added_at": datetime.utcnow().isoformat(),
                "original_text": text,
            },
        )

        logger.info(
            "Facebook paste parsed: %s (source_id=%s, price=%s)",
            title, source_id, price,
        )
        return listing
