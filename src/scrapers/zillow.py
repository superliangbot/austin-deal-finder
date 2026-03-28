"""Zillow rental scraper using httpx and embedded JSON extraction.

Zillow embeds listing data in a __NEXT_DATA__ JSON blob within
the page source. This scraper extracts and parses that data.
"""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Base Zillow rentals URL for Austin
BASE_URL = "https://www.zillow.com/austin-tx/rentals/"

# Regex to find the __NEXT_DATA__ script tag content
NEXT_DATA_PATTERN = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)

# Regex for price extraction as fallback
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")


class ZillowScraper(BaseScraper):
    """Scraper for Zillow Austin rental listings.

    Extracts listing data from the __NEXT_DATA__ JSON blob that
    Zillow embeds in page source. Uses careful headers to avoid blocking.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_price = settings.max_price

    def _build_headers(self) -> dict[str, str]:
        """Build request headers tuned for Zillow.

        Zillow has aggressive bot detection, so these headers
        mimic a real browser session as closely as possible.

        Returns:
            Headers dict optimized for Zillow requests.
        """
        headers = self._default_headers()
        headers.update({
            "Referer": "https://www.google.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Cache-Control": "max-age=0",
        })
        return headers

    def scrape(self) -> list[dict]:
        """Scrape rental listings from Zillow.

        Fetches the Austin rentals page, extracts the __NEXT_DATA__
        JSON blob, and parses individual listings from it.

        Returns:
            List of normalized listing dictionaries.
        """
        listings: list[dict] = []

        try:
            page_html = self._fetch_page()
            if not page_html:
                logger.warning("Failed to fetch Zillow page")
                return listings

            # Try to extract data from __NEXT_DATA__ JSON
            next_data = self._extract_next_data(page_html)
            if next_data:
                listings = self._parse_next_data(next_data)
            else:
                # Fallback: try parsing listing data from other script tags
                logger.warning("No __NEXT_DATA__ found, trying fallback parsing")
                listings = self._fallback_parse(page_html)

        except Exception:
            logger.exception("Error scraping Zillow")

        logger.info("Zillow scraper found %d listings", len(listings))
        return listings

    def _fetch_page(self) -> str | None:
        """Fetch the Zillow search results page.

        Returns:
            HTML content as string, or None if the request failed.
        """
        self._rotate_user_agent()
        headers = self._build_headers()

        try:
            response = self.client.get(BASE_URL, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            logger.exception("HTTP error fetching Zillow")
            return None

    def _extract_next_data(self, html: str) -> dict | None:
        """Extract the __NEXT_DATA__ JSON blob from page HTML.

        Args:
            html: Full page HTML content.

        Returns:
            Parsed JSON as dict, or None if not found.
        """
        match = NEXT_DATA_PATTERN.search(html)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.exception("Failed to parse __NEXT_DATA__ JSON")
                return None
        return None

    def _parse_next_data(self, data: dict) -> list[dict]:
        """Parse listings from the __NEXT_DATA__ JSON structure.

        Navigates the nested Zillow data structure to extract
        individual listing details.

        Args:
            data: Parsed __NEXT_DATA__ JSON.

        Returns:
            List of normalized listing dicts.
        """
        listings: list[dict] = []

        try:
            # Navigate the Zillow __NEXT_DATA__ structure
            # The path varies but typically follows:
            # props -> pageProps -> searchPageState -> cat1 -> searchResults -> listResults
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Try multiple known paths for the search results
            search_state = page_props.get("searchPageState", {})
            cat1 = search_state.get("cat1", {})
            search_results = cat1.get("searchResults", {})
            list_results = search_results.get("listResults", [])

            # Fallback path
            if not list_results:
                list_results = search_results.get("mapResults", [])

            for result in list_results:
                try:
                    listing = self._parse_listing_result(result)
                    if listing is not None:
                        listings.append(listing)
                except Exception:
                    logger.exception("Error parsing Zillow listing result")

        except Exception:
            logger.exception("Error navigating Zillow __NEXT_DATA__ structure")

        return listings

    def _parse_listing_result(self, result: dict) -> dict | None:
        """Parse a single Zillow listing result from JSON data.

        Args:
            result: Individual listing dict from Zillow JSON.

        Returns:
            Normalized listing dict, or None if not valid.
        """
        # Extract Zillow property ID
        zpid = result.get("zpid") or result.get("id")
        if zpid:
            source_id = str(zpid)
        else:
            source_id = None

        # Build listing URL
        detail_url = result.get("detailUrl")
        if detail_url and not detail_url.startswith("http"):
            source_url = f"https://www.zillow.com{detail_url}"
        else:
            source_url = detail_url

        # Extract price
        price = None
        price_data = result.get("price")
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

        # Also check unformattedPrice
        if price is None:
            unformatted = result.get("unformattedPrice")
            if isinstance(unformatted, (int, float)):
                price = float(unformatted)

        # Filter by max price
        if price is not None and price > self.max_price:
            return None

        # Extract address
        address = result.get("address")
        if isinstance(address, dict):
            # Address may be a structured object
            address = address.get("streetAddress", "")
            city = address if isinstance(address, str) else ""
        elif not isinstance(address, str):
            address = None

        # Also try addressStreet field
        if not address:
            address = result.get("addressStreet") or result.get("streetAddress")

        # Extract bedrooms, bathrooms, sqft
        bedrooms = result.get("beds")
        if isinstance(bedrooms, str):
            try:
                bedrooms = int(bedrooms)
            except ValueError:
                bedrooms = None

        bathrooms = result.get("baths")
        if isinstance(bathrooms, str):
            try:
                bathrooms = float(bathrooms)
            except ValueError:
                bathrooms = None

        sqft = result.get("area") or result.get("livingArea")
        if isinstance(sqft, str):
            try:
                sqft = int(sqft.replace(",", ""))
            except ValueError:
                sqft = None

        # Extract title (property name or address-based)
        title = result.get("buildingName") or result.get("statusText")
        if not title and address:
            title = f"Rental at {address}"

        # Extract images
        images: list[str] = []
        img_src = result.get("imgSrc") or result.get("image")
        if img_src:
            images.append(img_src)

        # Determine listing type
        listing_type = "apartment"
        status_type = result.get("statusType", "").lower()
        if "room" in status_type:
            listing_type = "roommate"

        raw_data = {
            "zpid": zpid,
            "statusText": result.get("statusText"),
            "statusType": result.get("statusType"),
            "latitude": result.get("latLong", {}).get("latitude") if isinstance(result.get("latLong"), dict) else None,
            "longitude": result.get("latLong", {}).get("longitude") if isinstance(result.get("latLong"), dict) else None,
            "has3DModel": result.get("has3DModel"),
            "hasVideo": result.get("hasVideo"),
        }

        return self.normalize_listing(
            source="zillow",
            source_id=source_id,
            source_url=source_url,
            title=title,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            address=address if isinstance(address, str) else None,
            listing_type=listing_type,
            images=images,
            raw_data=raw_data,
        )

    def _fallback_parse(self, html: str) -> list[dict]:
        """Fallback parser using BeautifulSoup if __NEXT_DATA__ is missing.

        Looks for other embedded JSON or parses listing cards directly
        from the HTML structure.

        Args:
            html: Full page HTML content.

        Returns:
            List of normalized listing dicts.
        """
        listings: list[dict] = []
        soup = BeautifulSoup(html, "html.parser")

        # Try to find listing data in any script tag with JSON
        for script_tag in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script_tag.string or "")
                if isinstance(data, dict) and ("searchResults" in str(data)[:500] or "listResults" in str(data)[:500]):
                    # Found potential listing data, try to parse it
                    results = self._find_list_results(data)
                    for result in results:
                        listing = self._parse_listing_result(result)
                        if listing is not None:
                            listings.append(listing)
            except (json.JSONDecodeError, TypeError):
                continue

        # If still no results, try parsing HTML listing cards
        if not listings:
            listing_cards = soup.select("[data-test='property-card']") or soup.select(".list-card")
            for card in listing_cards:
                try:
                    listing = self._parse_html_card(card)
                    if listing is not None:
                        listings.append(listing)
                except Exception:
                    logger.exception("Error parsing Zillow HTML card")

        return listings

    @staticmethod
    def _find_list_results(data: dict, depth: int = 0) -> list[dict]:
        """Recursively search a nested dict for a 'listResults' key.

        Args:
            data: Nested dictionary to search.
            depth: Current recursion depth (max 10).

        Returns:
            List of listing result dicts, or empty list.
        """
        if depth > 10:
            return []

        if "listResults" in data and isinstance(data["listResults"], list):
            return data["listResults"]

        for value in data.values():
            if isinstance(value, dict):
                result = ZillowScraper._find_list_results(value, depth + 1)
                if result:
                    return result

        return []

    def _parse_html_card(self, card) -> dict | None:
        """Parse a Zillow listing card from HTML as a last resort.

        Args:
            card: BeautifulSoup element for a listing card.

        Returns:
            Normalized listing dict, or None.
        """
        link_el = card.select_one("a[href]")
        if not link_el:
            return None

        href = link_el.get("href", "")
        source_url = href if href.startswith("http") else f"https://www.zillow.com{href}"

        # Try to extract zpid from URL
        source_id = None
        zpid_match = re.search(r"/(\d+)_zpid", href)
        if zpid_match:
            source_id = zpid_match.group(1)

        title = None
        addr_el = card.select_one("address") or card.select_one("[data-test='property-card-addr']")
        if addr_el:
            title = addr_el.get_text(strip=True)

        price = None
        price_el = card.select_one("[data-test='property-card-price']") or card.select_one(".list-card-price")
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

        return self.normalize_listing(
            source="zillow",
            source_id=source_id,
            source_url=source_url,
            title=title,
            price=price,
            listing_type="apartment",
            raw_data={"fallback_parse": True},
        )
