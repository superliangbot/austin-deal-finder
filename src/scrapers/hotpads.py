"""HotPads rental scraper using httpx and embedded JSON extraction.

HotPads (owned by Zillow Group) embeds listing data in JSON within
the page source, similar to Zillow's __NEXT_DATA__ pattern.
"""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Base HotPads search URL for Austin apartments
BASE_URL = "https://hotpads.com/austin-tx/apartments-for-rent"

# Regex for price extraction
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")

# Regex patterns for details
BEDS_PATTERN = re.compile(r"(\d+)\s*(?:bed|br|bedroom)", re.IGNORECASE)
BATHS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath|ba|bathroom)", re.IGNORECASE)
SQFT_PATTERN = re.compile(r"([\d,]+)\s*(?:sq\s*ft|sqft|sf)", re.IGNORECASE)


class HotPadsScraper(BaseScraper):
    """Scraper for HotPads Austin rental listings.

    Extracts listing data from embedded JSON in the page source
    or falls back to HTML parsing of listing cards.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_price = settings.max_price

    def _build_headers(self) -> dict[str, str]:
        """Build request headers for HotPads.

        Returns:
            Headers dict optimized for HotPads requests.
        """
        headers = self._default_headers()
        headers.update({
            "Referer": "https://www.google.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
        })
        return headers

    def scrape(self) -> list[dict]:
        """Scrape rental listings from HotPads.

        Fetches the Austin apartments page and extracts listing data
        from embedded JSON or falls back to HTML parsing.

        Returns:
            List of normalized listing dictionaries.
        """
        listings: list[dict] = []

        try:
            page_html = self._fetch_page()
            if not page_html:
                logger.warning("Failed to fetch HotPads page")
                return listings

            # Try to extract data from embedded JSON first
            json_listings = self._extract_json_listings(page_html)
            if json_listings:
                listings = json_listings
            else:
                # Fallback to HTML parsing
                logger.info("No embedded JSON found, falling back to HTML parsing")
                listings = self._parse_html_listings(page_html)

        except Exception:
            logger.exception("Error scraping HotPads")

        logger.info("HotPads scraper found %d listings", len(listings))
        return listings

    def _fetch_page(self) -> str | None:
        """Fetch the HotPads search results page.

        Returns:
            HTML content as string, or None if request failed.
        """
        self._rotate_user_agent()
        headers = self._build_headers()

        try:
            response = self.client.get(BASE_URL, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            logger.exception("HTTP error fetching HotPads")
            return None

    def _extract_json_listings(self, html: str) -> list[dict]:
        """Extract listings from embedded JSON in page source.

        HotPads may embed listing data in script tags as JSON-LD,
        __NEXT_DATA__, or other structured data formats.

        Args:
            html: Full page HTML content.

        Returns:
            List of normalized listing dicts, or empty list.
        """
        listings: list[dict] = []
        soup = BeautifulSoup(html, "html.parser")

        # Try __NEXT_DATA__ first (HotPads is a Next.js app)
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag and next_data_tag.string:
            try:
                data = json.loads(next_data_tag.string)
                listings = self._parse_next_data(data)
                if listings:
                    return listings
            except json.JSONDecodeError:
                logger.warning("Failed to parse HotPads __NEXT_DATA__")

        # Try finding JSON in other script tags
        for script_tag in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script_tag.string or "")
                if isinstance(data, dict):
                    found = self._find_listing_data(data)
                    if found:
                        for item in found:
                            listing = self._parse_json_listing(item)
                            if listing is not None:
                                listings.append(listing)
                        if listings:
                            return listings
            except (json.JSONDecodeError, TypeError):
                continue

        # Try JSON-LD structured data
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string or "")
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") in ("Apartment", "Residence", "Place"):
                            listing = self._parse_jsonld_listing(item)
                            if listing is not None:
                                listings.append(listing)
                elif isinstance(data, dict) and data.get("@type") in ("ItemList", "SearchResultsPage"):
                    items = data.get("itemListElement", [])
                    for item in items:
                        listing = self._parse_jsonld_listing(item.get("item", item))
                        if listing is not None:
                            listings.append(listing)
            except (json.JSONDecodeError, TypeError):
                continue

        return listings

    def _parse_next_data(self, data: dict) -> list[dict]:
        """Parse listings from a __NEXT_DATA__ JSON structure.

        Args:
            data: Parsed __NEXT_DATA__ JSON.

        Returns:
            List of normalized listing dicts.
        """
        listings: list[dict] = []

        try:
            # Navigate common Next.js data paths
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # HotPads may store listings under various keys
            search_data = (
                page_props.get("searchData", {})
                or page_props.get("listings", {})
                or page_props.get("results", {})
            )

            # Try to find listing arrays in the data
            listing_items = []
            if isinstance(search_data, dict):
                listing_items = (
                    search_data.get("listings", [])
                    or search_data.get("results", [])
                    or search_data.get("items", [])
                )
            elif isinstance(search_data, list):
                listing_items = search_data

            # Also try a deeper search if nothing found yet
            if not listing_items:
                listing_items = self._find_listing_data(page_props)

            for item in listing_items:
                try:
                    listing = self._parse_json_listing(item)
                    if listing is not None:
                        listings.append(listing)
                except Exception:
                    logger.exception("Error parsing HotPads listing from __NEXT_DATA__")

        except Exception:
            logger.exception("Error navigating HotPads __NEXT_DATA__ structure")

        return listings

    def _parse_json_listing(self, item: dict) -> dict | None:
        """Parse a single listing from HotPads JSON data.

        Args:
            item: Individual listing dict from JSON data.

        Returns:
            Normalized listing dict, or None.
        """
        # Extract listing ID
        source_id = str(
            item.get("listingId")
            or item.get("id")
            or item.get("maloneLotIdEncoded")
            or ""
        )
        if not source_id:
            return None

        # Build listing URL
        detail_path = item.get("detailUrl") or item.get("url") or item.get("path")
        if detail_path:
            if not detail_path.startswith("http"):
                source_url = f"https://hotpads.com{detail_path}"
            else:
                source_url = detail_path
        else:
            source_url = f"https://hotpads.com/listing/{source_id}"

        # Extract price
        price = None
        price_data = item.get("price") or item.get("highPrice") or item.get("lowPrice")
        if isinstance(price_data, (int, float)):
            price = float(price_data)
        elif isinstance(price_data, str):
            price_match = PRICE_PATTERN.search(price_data)
            if price_match:
                price_str = price_match.group(0).replace("$", "").replace(",", "").replace("/mo", "")
                try:
                    price = float(price_str)
                except ValueError:
                    pass

        # Filter by max price
        if price is not None and price > self.max_price:
            return None

        # Extract details
        title = item.get("name") or item.get("title") or item.get("buildingName")
        address = item.get("address") or item.get("streetAddress") or item.get("fullAddress")
        if isinstance(address, dict):
            address = address.get("streetAddress") or address.get("fullAddress")

        bedrooms = item.get("bedrooms") or item.get("beds")
        if isinstance(bedrooms, str):
            try:
                bedrooms = int(bedrooms)
            except ValueError:
                bedrooms = None

        bathrooms = item.get("bathrooms") or item.get("baths")
        if isinstance(bathrooms, str):
            try:
                bathrooms = float(bathrooms)
            except ValueError:
                bathrooms = None

        sqft = item.get("sqft") or item.get("area") or item.get("livingArea")
        if isinstance(sqft, str):
            try:
                sqft = int(sqft.replace(",", ""))
            except ValueError:
                sqft = None

        # Extract images
        images: list[str] = []
        photos = item.get("photos") or item.get("images") or []
        if isinstance(photos, list):
            for photo in photos[:10]:  # Limit to 10 images
                if isinstance(photo, str):
                    images.append(photo)
                elif isinstance(photo, dict):
                    img_url = photo.get("url") or photo.get("src") or photo.get("href")
                    if img_url:
                        images.append(img_url)

        # Determine if furnished
        furnished = None
        amenities = item.get("amenities", [])
        if isinstance(amenities, list):
            amenity_lower = [str(a).lower() for a in amenities]
            if any("furnish" in a for a in amenity_lower):
                furnished = True

        # Pets
        pets_allowed = None
        if isinstance(amenities, list):
            amenity_lower = [str(a).lower() for a in amenities]
            if any("pet" in a or "dog" in a or "cat" in a for a in amenity_lower):
                pets_allowed = True

        if not title and address:
            title = f"Rental at {address}"

        raw_data = {
            "listingId": item.get("listingId"),
            "latitude": item.get("latitude") or item.get("lat"),
            "longitude": item.get("longitude") or item.get("lng") or item.get("lon"),
            "listingType": item.get("listingType"),
            "amenities": amenities[:20] if isinstance(amenities, list) else None,
        }

        return self.normalize_listing(
            source="hotpads",
            source_id=source_id,
            source_url=source_url,
            title=title,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            address=address if isinstance(address, str) else None,
            listing_type="apartment",
            furnished=furnished,
            pets_allowed=pets_allowed,
            images=images,
            raw_data=raw_data,
        )

    def _parse_jsonld_listing(self, item: dict) -> dict | None:
        """Parse a listing from JSON-LD structured data.

        Args:
            item: JSON-LD item dict.

        Returns:
            Normalized listing dict, or None.
        """
        source_url = item.get("url")
        source_id = None
        if source_url:
            # Try to extract an ID from the URL
            parts = source_url.rstrip("/").split("/")
            if parts:
                source_id = parts[-1]

        name = item.get("name")
        address = item.get("address")
        if isinstance(address, dict):
            address = address.get("streetAddress")

        return self.normalize_listing(
            source="hotpads",
            source_id=source_id,
            source_url=source_url,
            title=name,
            address=address if isinstance(address, str) else None,
            listing_type="apartment",
            raw_data={"jsonld": True},
        )

    @staticmethod
    def _find_listing_data(data: dict, depth: int = 0) -> list[dict]:
        """Recursively search for listing arrays in nested data.

        Args:
            data: Nested dictionary to search.
            depth: Current recursion depth (max 8).

        Returns:
            List of listing dicts if found, otherwise empty list.
        """
        if depth > 8:
            return []

        # Check common keys that hold listing arrays
        for key in ("listings", "results", "items", "searchResults", "listResults"):
            if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                # Verify the items look like listings (have price or address)
                first = data[key][0]
                if isinstance(first, dict) and any(
                    k in first for k in ("price", "address", "listingId", "id", "beds", "bedrooms")
                ):
                    return data[key]

        # Recurse into nested dicts
        for value in data.values():
            if isinstance(value, dict):
                result = HotPadsScraper._find_listing_data(value, depth + 1)
                if result:
                    return result

        return []

    def _parse_html_listings(self, html: str) -> list[dict]:
        """Fallback: parse listings from HTML structure.

        Used when no embedded JSON data can be found.

        Args:
            html: Full page HTML content.

        Returns:
            List of normalized listing dicts.
        """
        listings: list[dict] = []
        soup = BeautifulSoup(html, "html.parser")

        # HotPads listing cards
        cards = (
            soup.select("[data-test='listing-card']")
            or soup.select(".ListingCard")
            or soup.select("[class*='ListingCard']")
            or soup.select("article")
        )

        for card in cards:
            try:
                listing = self._parse_html_card(card)
                if listing is not None:
                    listings.append(listing)
            except Exception:
                logger.exception("Error parsing HotPads HTML card")

        return listings

    def _parse_html_card(self, card) -> dict | None:
        """Parse a single HotPads listing card from HTML.

        Args:
            card: BeautifulSoup element for a listing card.

        Returns:
            Normalized listing dict, or None.
        """
        # Extract link
        link_el = card.select_one("a[href]")
        if not link_el:
            return None

        href = link_el.get("href", "")
        if not href:
            return None

        source_url = href if href.startswith("http") else f"https://hotpads.com{href}"

        # Extract source ID from URL
        source_id = href.rstrip("/").split("/")[-1] if href else None

        # Extract title
        title = None
        title_el = card.select_one("[data-test='listing-card-title']") or card.select_one("h2") or card.select_one("h3")
        if title_el:
            title = title_el.get_text(strip=True)

        # Extract price
        price = None
        price_el = card.select_one("[data-test='listing-card-price']") or card.select_one("[class*='price']")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_match = PRICE_PATTERN.search(price_text)
            if price_match:
                price_str = price_match.group(0).replace("$", "").replace(",", "").replace("/mo", "")
                try:
                    price = float(price_str)
                except ValueError:
                    pass

        if price is not None and price > self.max_price:
            return None

        # Extract address
        address = None
        addr_el = card.select_one("[data-test='listing-card-address']") or card.select_one("[class*='address']")
        if addr_el:
            address = addr_el.get_text(strip=True)

        # Extract details text for beds/baths/sqft
        bedrooms = None
        bathrooms = None
        sqft = None
        details_el = card.select_one("[data-test='listing-card-details']") or card.select_one("[class*='details']")
        if details_el:
            details_text = details_el.get_text(strip=True)
            beds_match = BEDS_PATTERN.search(details_text)
            if beds_match:
                try:
                    bedrooms = int(beds_match.group(1))
                except ValueError:
                    pass
            baths_match = BATHS_PATTERN.search(details_text)
            if baths_match:
                try:
                    bathrooms = float(baths_match.group(1))
                except ValueError:
                    pass
            sqft_match = SQFT_PATTERN.search(details_text)
            if sqft_match:
                try:
                    sqft = int(sqft_match.group(1).replace(",", ""))
                except ValueError:
                    pass

        return self.normalize_listing(
            source="hotpads",
            source_id=source_id,
            source_url=source_url,
            title=title,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            address=address,
            listing_type="apartment",
            raw_data={"html_parse": True},
        )
