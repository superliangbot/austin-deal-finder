"""Abstract base scraper with shared utilities for all scrapers."""

import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Common user agents for rotation to reduce blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]


class BaseScraper(ABC):
    """Abstract base class for all scrapers.

    Provides common utilities for HTTP requests, rate limiting,
    user agent rotation, and listing normalization.
    """

    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=self._default_headers(),
            follow_redirects=True,
        )

    def _default_headers(self) -> dict[str, str]:
        """Return default HTTP headers with a random user agent."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _rotate_user_agent(self) -> None:
        """Set a new random user agent on the client."""
        self.client.headers["User-Agent"] = random.choice(USER_AGENTS)

    @staticmethod
    def random_delay(min_seconds: float = 2.0, max_seconds: float = 8.0) -> None:
        """Sleep for a random duration to avoid rate limiting.

        Args:
            min_seconds: Minimum delay in seconds.
            max_seconds: Maximum delay in seconds.
        """
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug("Sleeping for %.2f seconds", delay)
        time.sleep(delay)

    @staticmethod
    def normalize_listing(
        source: str,
        source_id: str | None = None,
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
        """Create a normalized listing dictionary matching the Listing model fields.

        Args:
            source: Source platform name (e.g., "reddit", "craigslist").
            source_id: Unique identifier from the source platform.
            source_url: Direct URL to the listing.
            title: Listing title.
            description: Full listing description text.
            price: Monthly rent price.
            bedrooms: Number of bedrooms.
            bathrooms: Number of bathrooms.
            sqft: Square footage.
            address: Street address or location description.
            listing_type: Type of listing (apartment, sublease, roommate, etc.).
            furnished: Whether the unit is furnished.
            pets_allowed: Whether pets are allowed.
            available_date: Date when the unit is available (ISO format string).
            contact_info: Contact information for the listing.
            images: List of image URLs.
            raw_data: Full raw data from the source for archival.

        Returns:
            Normalized dictionary with all standard listing fields.
        """
        return {
            "source": source,
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

    @abstractmethod
    def scrape(self) -> list[dict]:
        """Scrape listings from the source.

        Returns:
            List of normalized listing dictionaries.
        """
        ...

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
