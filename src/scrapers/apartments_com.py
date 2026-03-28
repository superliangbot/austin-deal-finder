"""Apartments.com scraper using httpx and BeautifulSoup.

Scrapes rental listings from Apartments.com for Austin, TX
filtered to under $2,000/month.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Base search URL filtered by price
BASE_URL = "https://www.apartments.com/austin-tx/under-{max_price}/"

# Regex patterns for parsing
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")
BEDS_PATTERN = re.compile(r"(\d+)\s*(?:bed|br|bedroom)", re.IGNORECASE)
BATHS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath|ba|bathroom)", re.IGNORECASE)
SQFT_PATTERN = re.compile(r"([\d,]+)\s*(?:sq\s*ft|sqft|sf)", re.IGNORECASE)


class ApartmentsComScraper(BaseScraper):
    """Scraper for Apartments.com Austin rental listings.

    Fetches server-rendered HTML from Apartments.com and parses
    listing cards for price, beds, baths, address, and other details.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_price = settings.max_price
        self.search_url = BASE_URL.format(max_price=self.max_price)

    def _build_headers(self) -> dict[str, str]:
        """Build request headers specific to Apartments.com.

        Returns:
            Headers dict with referer and other properties
            that help avoid being blocked.
        """
        headers = self._default_headers()
        headers.update({
            "Referer": "https://www.apartments.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })
        return headers

    def scrape(self) -> list[dict]:
        """Scrape rental listings from Apartments.com.

        Fetches the search results page and parses listing cards.
        Paginates through up to 5 pages of results.

        Returns:
            List of normalized listing dictionaries.
        """
        listings: list[dict] = []
        seen_ids: set[str] = set()

        # Scrape up to 5 pages
        for page_num in range(1, 6):
            try:
                page_listings = self._scrape_page(page_num)
                if not page_listings:
                    logger.debug("No listings on page %d, stopping pagination", page_num)
                    break

                for listing in page_listings:
                    sid = listing["source_id"]
                    if sid and sid not in seen_ids:
                        seen_ids.add(sid)
                        listings.append(listing)

            except Exception:
                logger.exception("Error scraping Apartments.com page %d", page_num)
                break

            # Delay between page requests
            self.random_delay(min_seconds=2.0, max_seconds=5.0)

        logger.info("Apartments.com scraper found %d unique listings", len(listings))
        return listings

    def _scrape_page(self, page_num: int) -> list[dict]:
        """Scrape a single page of Apartments.com results.

        Args:
            page_num: Page number to scrape (1-indexed).

        Returns:
            List of normalized listing dicts from this page.
        """
        url = self.search_url
        if page_num > 1:
            url = f"{self.search_url}{page_num}/"

        self._rotate_user_agent()
        headers = self._build_headers()

        try:
            response = self.client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("HTTP error fetching Apartments.com page %d", page_num)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict] = []

        # Apartments.com uses placard elements for listing cards
        listing_cards = soup.select("article.placard") or soup.select("li.mortar-wrapper")

        # Fallback: try generic listing card selectors
        if not listing_cards:
            listing_cards = soup.select("[data-listingid]")

        for card in listing_cards:
            try:
                listing = self._parse_listing_card(card)
                if listing is not None:
                    results.append(listing)
            except Exception:
                logger.exception("Error parsing Apartments.com listing card")

        return results

    def _parse_listing_card(self, card) -> dict | None:
        """Parse a single Apartments.com listing card.

        Args:
            card: BeautifulSoup element for one listing card.

        Returns:
            Normalized listing dict, or None if parsing fails.
        """
        # Extract listing ID from data attribute
        source_id = card.get("data-listingid") or card.get("data-id")

        # Extract the listing URL
        link_el = card.select_one("a.property-link") or card.select_one("a[href]")
        source_url = None
        if link_el:
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                source_url = f"https://www.apartments.com{href}"
            else:
                source_url = href

        # If no source_id from data attribute, derive from URL
        if not source_id and source_url:
            # URL pattern: /apartments-name/slug/
            url_parts = source_url.rstrip("/").split("/")
            if url_parts:
                source_id = url_parts[-1]

        # Extract title (property name)
        title = None
        title_el = (
            card.select_one(".property-title")
            or card.select_one(".placard-header-title")
            or card.select_one("span.js-placardTitle")
        )
        if title_el:
            title = title_el.get_text(strip=True)

        # Extract price
        price = None
        price_el = card.select_one(".property-pricing") or card.select_one(".price-range")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price = self._parse_price(price_text)

        # Skip if price exceeds max
        if price is not None and price > self.max_price:
            return None

        # Extract address
        address = None
        addr_el = card.select_one(".property-address") or card.select_one("div.location")
        if addr_el:
            address = addr_el.get_text(strip=True)

        # Extract beds, baths, sqft from the details section
        bedrooms = None
        bathrooms = None
        sqft = None
        details_el = card.select_one(".property-beds") or card.select_one(".bed-range")
        if details_el:
            details_text = details_el.get_text(strip=True)
            bedrooms, bathrooms, sqft = self._parse_details(details_text)

        # Also check for separate sqft element
        if sqft is None:
            sqft_el = card.select_one(".property-sqft") or card.select_one(".sqft-range")
            if sqft_el:
                sqft_text = sqft_el.get_text(strip=True)
                sqft_match = SQFT_PATTERN.search(sqft_text)
                if sqft_match:
                    try:
                        sqft = int(sqft_match.group(1).replace(",", ""))
                    except ValueError:
                        pass

        # Extract images
        images: list[str] = []
        img_els = card.select("img")
        for img in img_els:
            src = img.get("data-src") or img.get("src")
            if src and "placeholder" not in src.lower():
                images.append(src)

        raw_data = {
            "page_url": self.search_url,
            "data_listingid": card.get("data-listingid"),
        }

        return self.normalize_listing(
            source="apartments_com",
            source_id=source_id,
            source_url=source_url,
            title=title,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            address=address,
            listing_type="apartment",
            images=images,
            raw_data=raw_data,
        )

    @staticmethod
    def _parse_price(text: str) -> float | None:
        """Parse a price from text, handling ranges by taking the lower end.

        Args:
            text: Text containing a price (e.g., "$1,200", "$1,100 - $1,500").

        Returns:
            Price as a float, or None if parsing fails.
        """
        if not text:
            return None

        # Find all price matches and take the first (lowest in a range)
        matches = PRICE_PATTERN.findall(text)
        if matches:
            price_str = matches[0].replace("$", "").replace(",", "").replace("/mo", "")
            try:
                return float(price_str)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_details(text: str) -> tuple[int | None, float | None, int | None]:
        """Parse bedrooms, bathrooms, and sqft from a details string.

        Args:
            text: Details text like "1 Bed, 1 Bath, 650 Sq Ft".

        Returns:
            Tuple of (bedrooms, bathrooms, sqft).
        """
        bedrooms = None
        bathrooms = None
        sqft = None

        # Handle "Studio" as 0 bedrooms
        if "studio" in text.lower():
            bedrooms = 0

        beds_match = BEDS_PATTERN.search(text)
        if beds_match:
            try:
                bedrooms = int(beds_match.group(1))
            except ValueError:
                pass

        baths_match = BATHS_PATTERN.search(text)
        if baths_match:
            try:
                bathrooms = float(baths_match.group(1))
            except ValueError:
                pass

        sqft_match = SQFT_PATTERN.search(text)
        if sqft_match:
            try:
                sqft = int(sqft_match.group(1).replace(",", ""))
            except ValueError:
                pass

        return bedrooms, bathrooms, sqft
