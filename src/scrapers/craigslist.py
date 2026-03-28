"""Craigslist Austin scraper using httpx and BeautifulSoup.

Scrapes apartment, room/shared, and sublet listings from
Craigslist Austin with anti-blocking measures.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Craigslist search URLs for Austin housing categories
SEARCH_URLS = [
    "https://austin.craigslist.org/search/apa",  # Apartments / Housing
    "https://austin.craigslist.org/search/roo",  # Rooms / Shared
    "https://austin.craigslist.org/search/sub",  # Sublets / Temporary
]

# Regex to extract price from text
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")

# Regex to extract source ID from Craigslist URL path (e.g., /apa/d/title/12345678.html)
SOURCE_ID_PATTERN = re.compile(r"/(\d+)\.html")

# Category slug to listing type mapping
CATEGORY_TYPE_MAP = {
    "apa": "apartment",
    "roo": "roommate",
    "sub": "sublease",
}


class CraigslistScraper(BaseScraper):
    """Scraper for Craigslist Austin housing listings.

    Fetches and parses static HTML from multiple Craigslist housing
    categories with user agent rotation and random delays between requests.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_price = settings.max_price

    def scrape(self) -> list[dict]:
        """Scrape housing listings from Craigslist Austin.

        Iterates through apartment, rooms, and sublet categories,
        respecting rate limits with random delays between requests.

        Returns:
            List of normalized listing dictionaries.
        """
        listings: list[dict] = []
        seen_ids: set[str] = set()

        for url in SEARCH_URLS:
            try:
                results = self._scrape_category(url)
                for listing in results:
                    sid = listing["source_id"]
                    if sid and sid not in seen_ids:
                        seen_ids.add(sid)
                        listings.append(listing)
            except Exception:
                logger.exception("Error scraping Craigslist category: %s", url)

            # Delay between category requests
            self.random_delay(min_seconds=2.0, max_seconds=5.0)

        logger.info("Craigslist scraper found %d unique listings", len(listings))
        return listings

    def _scrape_category(self, url: str) -> list[dict]:
        """Scrape a single Craigslist search category.

        Args:
            url: Craigslist search URL for the category.

        Returns:
            List of normalized listing dicts from this category.
        """
        results: list[dict] = []

        # Determine category from URL for listing_type mapping
        category = url.rstrip("/").split("/")[-1]
        listing_type = CATEGORY_TYPE_MAP.get(category)

        # Apply price filter via query parameters
        params = {
            "max_price": str(self.max_price),
            "availabilityMode": "0",
            "sale_date": "all+dates",
        }

        self._rotate_user_agent()

        try:
            response = self.client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("HTTP error fetching %s", url)
            return results

        soup = BeautifulSoup(response.text, "html.parser")

        # Parse listing rows from search results
        # Craigslist uses <li class="cl-static-search-result"> for listings
        listing_rows = soup.select("li.cl-static-search-result")

        # Fallback: try older Craigslist HTML structure
        if not listing_rows:
            listing_rows = soup.select(".result-row")

        # Another fallback: try gallery card structure
        if not listing_rows:
            listing_rows = soup.select(".cl-search-result")

        for row in listing_rows:
            try:
                listing = self._parse_listing_row(row, listing_type)
                if listing is not None:
                    results.append(listing)
            except Exception:
                logger.exception("Error parsing Craigslist listing row")

            # Small delay between parsing operations (minimal, just for safety)
            self.random_delay(min_seconds=0.1, max_seconds=0.3)

        # Check for additional pages and scrape them (up to 3 pages total)
        for page in range(1, 3):
            next_url = self._get_next_page_url(soup, url)
            if not next_url:
                break

            self.random_delay(min_seconds=2.0, max_seconds=5.0)
            self._rotate_user_agent()

            try:
                response = self.client.get(next_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                page_rows = (
                    soup.select("li.cl-static-search-result")
                    or soup.select(".result-row")
                    or soup.select(".cl-search-result")
                )

                for row in page_rows:
                    try:
                        listing = self._parse_listing_row(row, listing_type)
                        if listing is not None:
                            results.append(listing)
                    except Exception:
                        logger.exception("Error parsing Craigslist listing row on page %d", page + 1)
            except httpx.HTTPError:
                logger.exception("HTTP error fetching page %d: %s", page + 1, next_url)
                break

        return results

    def _parse_listing_row(self, row, listing_type: str | None) -> dict | None:
        """Parse a single Craigslist listing row into a normalized dict.

        Args:
            row: BeautifulSoup element for one listing row.
            listing_type: Type of listing based on category.

        Returns:
            Normalized listing dict, or None if parsing fails.
        """
        # Extract the link and title
        link_el = row.select_one("a")
        if not link_el:
            return None

        title = link_el.get_text(strip=True)
        href = link_el.get("href", "")

        # Build full URL if relative
        if href and not href.startswith("http"):
            source_url = f"https://austin.craigslist.org{href}"
        else:
            source_url = href

        # Extract source ID from URL
        source_id = None
        id_match = SOURCE_ID_PATTERN.search(href)
        if id_match:
            source_id = id_match.group(1)

        # Extract price
        price = None
        price_el = row.select_one(".priceinfo") or row.select_one(".result-price")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_match = PRICE_PATTERN.search(price_text)
            if price_match:
                price_str = price_match.group(0).replace("$", "").replace(",", "").replace("/mo", "")
                try:
                    price = float(price_str)
                except ValueError:
                    pass

        # Fallback: extract price from title
        if price is None:
            price_match = PRICE_PATTERN.search(title)
            if price_match:
                price_str = price_match.group(0).replace("$", "").replace(",", "").replace("/mo", "")
                try:
                    price = float(price_str)
                except ValueError:
                    pass

        # Skip if price exceeds max
        if price is not None and price > self.max_price:
            return None

        # Extract location/neighborhood
        address = None
        location_el = row.select_one(".result-hood") or row.select_one(".meta")
        if location_el:
            address = location_el.get_text(strip=True).strip("() ")

        # Extract housing details (beds, sqft) if present
        bedrooms = None
        sqft = None
        housing_el = row.select_one(".housing")
        if housing_el:
            housing_text = housing_el.get_text(strip=True)
            br_match = re.search(r"(\d+)br", housing_text)
            if br_match:
                bedrooms = int(br_match.group(1))
            sqft_match = re.search(r"(\d+)\s*ft", housing_text)
            if sqft_match:
                sqft = int(sqft_match.group(1))

        # Extract posting date
        date_el = row.select_one("time") or row.select_one(".result-date")
        posting_date = None
        if date_el:
            posting_date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Extract images (thumbnail from gallery if present)
        images: list[str] = []
        img_els = row.select("img")
        for img in img_els:
            src = img.get("src") or img.get("data-src")
            if src:
                images.append(src)

        raw_data = {
            "category": listing_type,
            "href": href,
            "posting_date": posting_date,
            "full_html": str(row)[:2000],  # Truncate to avoid huge raw_data
        }

        return self.normalize_listing(
            source="craigslist",
            source_id=source_id,
            source_url=source_url,
            title=title,
            price=price,
            bedrooms=bedrooms,
            sqft=sqft,
            address=address,
            listing_type=listing_type,
            images=images,
            raw_data=raw_data,
        )

    @staticmethod
    def _get_next_page_url(soup: BeautifulSoup, current_url: str) -> str | None:
        """Find the URL for the next page of results.

        Args:
            soup: Parsed HTML of the current page.
            current_url: URL of the current page.

        Returns:
            URL for the next page, or None if no next page exists.
        """
        next_link = soup.select_one("a.button.next") or soup.select_one(".cl-next-page")
        if next_link and next_link.get("href"):
            href = next_link["href"]
            if not href.startswith("http"):
                return f"https://austin.craigslist.org{href}"
            return href
        return None
