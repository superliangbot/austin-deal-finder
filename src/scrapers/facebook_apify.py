"""Facebook scraper using Apify actors.

Uses Apify's Facebook Groups Scraper and Facebook Marketplace Scraper
to pull housing listings from Austin-area Facebook groups and marketplace.
Requires APIFY_API_TOKEN in environment.
"""

import logging
import os
import re
from datetime import datetime, timezone

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Regex to extract price from text
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:\s*/\s*(?:mo|month))?")

# Austin Facebook Groups for housing (public/semi-public groups)
FACEBOOK_GROUPS = [
    # UT Austin housing groups
    "https://www.facebook.com/groups/UTAustinHousingSublets",
    "https://www.facebook.com/groups/utaustinsubleases",
    # Austin general housing
    "https://www.facebook.com/groups/austinhousing",
    "https://www.facebook.com/groups/AustinRoommates",
    "https://www.facebook.com/groups/austintxapartments",
]

# Facebook Marketplace search config
MARKETPLACE_LOCATION = "austin"
MARKETPLACE_CATEGORY = "propertyrentals"


def _extract_price(text: str) -> float | None:
    """Extract price from text."""
    if not text:
        return None
    match = PRICE_PATTERN.search(text)
    if match:
        price_str = match.group(0)
        price_str = re.sub(r"[$/,\s]", "", price_str)
        price_str = re.sub(r"(mo|month)", "", price_str)
        try:
            return float(price_str)
        except ValueError:
            return None
    return None


def _detect_listing_type(text: str) -> str | None:
    """Detect listing type from text."""
    text_lower = text.lower()
    if "sublease" in text_lower or "sublet" in text_lower:
        return "sublease"
    if "lease takeover" in text_lower or "take over" in text_lower:
        return "lease_takeover"
    if "roommate" in text_lower or "room for rent" in text_lower:
        return "roommate"
    if any(kw in text_lower for kw in ["apartment", "studio", "1br", "2br", "1 bed", "2 bed"]):
        return "apartment"
    return None


class FacebookApifyScraper(BaseScraper):
    """Scraper for Facebook housing listings via Apify actors.

    Uses two Apify actors:
    1. Facebook Groups Scraper — for group posts
    2. Facebook Marketplace Scraper — for marketplace listings

    Requires APIFY_API_TOKEN environment variable.
    """

    def __init__(self) -> None:
        super().__init__()
        self.api_token = os.environ.get("APIFY_API_TOKEN", "")

    def _get_client(self):
        """Lazy-load Apify client."""
        from apify_client import ApifyClient
        return ApifyClient(self.api_token)

    def scrape(self) -> list[dict]:
        """Scrape Facebook groups and marketplace for Austin housing.

        Returns:
            List of normalized listing dictionaries.
        """
        if not self.api_token:
            logger.warning("APIFY_API_TOKEN not set. Skipping Facebook scraping.")
            return []

        listings: list[dict] = []
        seen_ids: set[str] = set()

        # Scrape Facebook Groups
        group_listings = self._scrape_groups()
        for listing in group_listings:
            sid = listing.get("source_id", "")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                listings.append(listing)

        # Scrape Facebook Marketplace
        marketplace_listings = self._scrape_marketplace()
        for listing in marketplace_listings:
            sid = listing.get("source_id", "")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                listings.append(listing)

        logger.info("Facebook Apify scraper found %d unique listings", len(listings))
        return listings

    def _scrape_groups(self) -> list[dict]:
        """Scrape Facebook Groups for housing posts."""
        results: list[dict] = []

        try:
            client = self._get_client()

            # Use the Facebook Groups Posts scraper
            # Actor: apify/facebook-groups-scraper
            run_input = {
                "startUrls": [{"url": url} for url in FACEBOOK_GROUPS],
                "maxPosts": 50,  # per group
                "maxPostComments": 0,  # skip comments to save credits
            }

            logger.info("Running Apify Facebook Groups scraper for %d groups...", len(FACEBOOK_GROUPS))
            run = client.actor("apify/facebook-groups-scraper").call(run_input=run_input)

            # Fetch results
            dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items

            for item in dataset_items:
                listing = self._parse_group_post(item)
                if listing is not None:
                    results.append(listing)

            logger.info("Facebook Groups: found %d relevant posts", len(results))

        except Exception:
            logger.exception("Error running Facebook Groups Apify scraper")

        return results

    def _scrape_marketplace(self) -> list[dict]:
        """Scrape Facebook Marketplace for rental listings."""
        results: list[dict] = []

        try:
            client = self._get_client()

            # Use Facebook Marketplace scraper
            # Actor: apify/facebook-marketplace-scraper
            run_input = {
                "searchQuery": "apartment rent",
                "location": "Austin, Texas",
                "category": "propertyrentals",
                "maxItems": 100,
                "maxPrice": 2000,
            }

            logger.info("Running Apify Facebook Marketplace scraper...")
            run = client.actor("apify/facebook-marketplace-scraper").call(run_input=run_input)

            dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items

            for item in dataset_items:
                listing = self._parse_marketplace_item(item)
                if listing is not None:
                    results.append(listing)

            logger.info("Facebook Marketplace: found %d listings", len(results))

        except Exception:
            logger.exception("Error running Facebook Marketplace Apify scraper")

        return results

    def _parse_group_post(self, item: dict) -> dict | None:
        """Parse a Facebook group post into a normalized listing."""
        try:
            text = item.get("text", "") or item.get("message", "") or ""
            title = text[:120] if text else "Untitled"

            # Filter: must be housing-related
            housing_keywords = [
                "sublease", "sublet", "rent", "apartment", "room",
                "lease", "housing", "bedroom", "studio", "move in",
                "available", "looking for", "1br", "2br", "1 bed",
                "furnished", "utilities", "deposit",
            ]
            text_lower = text.lower()
            if not any(kw in text_lower for kw in housing_keywords):
                return None

            price = _extract_price(text)
            # Also check if price is in structured data
            if not price and item.get("price"):
                try:
                    price = float(str(item["price"]).replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    pass

            listing_type = _detect_listing_type(text)

            source_url = item.get("url") or item.get("postUrl") or ""
            source_id = item.get("postId") or item.get("id") or ""

            # Images
            images = []
            if item.get("images"):
                images = item["images"] if isinstance(item["images"], list) else [item["images"]]
            elif item.get("photoUrl"):
                images = [item["photoUrl"]]

            # Contact info
            author = item.get("authorName") or item.get("user", {}).get("name", "")
            contact_info = author if author else None

            raw_data = {
                "group_name": item.get("groupName", ""),
                "author": author,
                "reactions": item.get("reactionsCount", 0),
                "comments": item.get("commentsCount", 0),
                "full_text": text,
            }

            return self.normalize_listing(
                source="facebook_group",
                source_id=str(source_id),
                source_url=source_url,
                title=title,
                description=text,
                price=price,
                listing_type=listing_type,
                contact_info=contact_info,
                images=images,
                raw_data=raw_data,
            )

        except Exception:
            logger.exception("Error parsing Facebook group post")
            return None

    def _parse_marketplace_item(self, item: dict) -> dict | None:
        """Parse a Facebook Marketplace item into a normalized listing."""
        try:
            title = item.get("title", "") or item.get("name", "")
            description = item.get("description", "") or ""

            # Price extraction
            price = None
            price_raw = item.get("price") or item.get("priceText", "")
            if price_raw:
                price_str = str(price_raw).replace("$", "").replace(",", "").replace("/mo", "").strip()
                # Handle "1,200/month" etc
                price_str = re.sub(r"[^0-9.]", "", price_str)
                try:
                    price = float(price_str) if price_str else None
                except ValueError:
                    price = _extract_price(str(price_raw))

            if not price:
                price = _extract_price(f"{title} {description}")

            # Skip if over budget
            if price and price > 2000:
                return None

            source_url = item.get("url") or item.get("itemUrl") or ""
            source_id = item.get("id") or item.get("itemId") or ""

            address = item.get("location") or item.get("locationText") or ""

            listing_type = _detect_listing_type(f"{title} {description}") or "apartment"

            images = []
            if item.get("images"):
                imgs = item["images"]
                if isinstance(imgs, list):
                    images = [i if isinstance(i, str) else i.get("url", "") for i in imgs]
            elif item.get("imageUrl"):
                images = [item["imageUrl"]]

            raw_data = {
                "seller": item.get("sellerName", ""),
                "seller_url": item.get("sellerUrl", ""),
                "condition": item.get("condition", ""),
                "listed_at": item.get("listedAt", ""),
            }

            return self.normalize_listing(
                source="facebook_marketplace",
                source_id=str(source_id),
                source_url=source_url,
                title=title,
                description=description,
                price=price,
                address=address,
                listing_type=listing_type,
                images=images,
                raw_data=raw_data,
            )

        except Exception:
            logger.exception("Error parsing Facebook Marketplace item")
            return None
