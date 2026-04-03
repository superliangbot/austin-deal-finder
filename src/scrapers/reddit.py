"""Reddit scraper using public JSON endpoints.

Searches housing-related subreddits for Austin area listings
including subleases, apartments, roommate situations, and lease takeovers.
"""

import logging
import re
import time
from datetime import datetime, timezone

import httpx

from src.config import settings
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Subreddits to search for Austin housing posts
SUBREDDITS = [
    "AustinHousing",
    "Austin",
    "UTAustin",
    "austinjobs",       # people post housing alongside job searches
    "Urbanism",         # Austin housing market discussions with deals info
    "AustinClassifieds",
]

# Search terms for finding housing-related posts
SEARCH_TERMS = [
    "sublease",
    "apartment",
    "housing",
    "roommate",
    "lease takeover",
    "rent",
    "new build",
    "move-in special",
    "free month",
    "lease special",
]

# Regex to extract price from text (e.g., $1,200, $1200/mo, $950)
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")

# Delay between requests to respect Reddit rate limits (2-3 seconds)
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 3.0


def _extract_price(text: str) -> float | None:
    """Extract the first dollar amount from text.

    Args:
        text: Text that may contain a price like "$1,200" or "$1200/mo".

    Returns:
        Price as a float, or None if no price found.
    """
    if not text:
        return None
    match = PRICE_PATTERN.search(text)
    if match:
        price_str = match.group(0)
        # Remove $, commas, and /mo suffix
        price_str = price_str.replace("$", "").replace(",", "").replace("/mo", "")
        try:
            return float(price_str)
        except ValueError:
            return None
    return None


def _detect_listing_type(text: str) -> str | None:
    """Detect the type of listing from the text content.

    Args:
        text: Combined title and body text.

    Returns:
        Listing type string or None.
    """
    text_lower = text.lower()
    if "sublease" in text_lower or "sublet" in text_lower:
        return "sublease"
    if "lease takeover" in text_lower or "take over" in text_lower:
        return "lease_takeover"
    if "roommate" in text_lower or "room for rent" in text_lower:
        return "roommate"
    if "apartment" in text_lower or "studio" in text_lower or "1br" in text_lower:
        return "apartment"
    return None


class RedditScraper(BaseScraper):
    """Scraper for Reddit housing posts using public JSON endpoints.

    Searches multiple Austin-area subreddits for housing-related posts
    and extracts listing information from post titles and bodies.
    """

    def __init__(self) -> None:
        super().__init__()
        self.user_agent = settings.reddit_user_agent
        self.http = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "User-Agent": self.user_agent,
            },
            follow_redirects=True,
        )

    def scrape(self) -> list[dict]:
        """Scrape housing listings from Reddit.

        Fetches new posts and searches for housing terms across
        configured subreddits.

        Returns:
            List of normalized listing dictionaries.
        """
        listings: list[dict] = []
        seen_ids: set[str] = set()

        for subreddit_name in SUBREDDITS:
            # Fetch new posts from the subreddit
            try:
                new_posts = self._fetch_new_posts(subreddit_name)
                for listing in new_posts:
                    if listing["source_id"] not in seen_ids:
                        seen_ids.add(listing["source_id"])
                        listings.append(listing)
            except Exception:
                logger.exception("Error fetching new posts from r/%s", subreddit_name)

            # Search for each term
            for term in SEARCH_TERMS:
                try:
                    results = self._search_subreddit(subreddit_name, term)
                    for listing in results:
                        if listing["source_id"] not in seen_ids:
                            seen_ids.add(listing["source_id"])
                            listings.append(listing)
                except Exception:
                    logger.exception(
                        "Error searching r/%s for '%s'", subreddit_name, term
                    )

        logger.info("Reddit scraper found %d unique listings", len(listings))
        return listings

    def _fetch_new_posts(self, subreddit_name: str) -> list[dict]:
        """Fetch newest posts from a subreddit via PullPush API.

        Args:
            subreddit_name: Name of the subreddit (without r/ prefix).

        Returns:
            List of normalized listing dicts from new posts.
        """
        url = "https://api.pullpush.io/reddit/search/submission/"
        params = {
            "subreddit": subreddit_name,
            "size": 100,
            "sort": "desc",
            "sort_type": "created_utc",
        }
        return self._fetch_and_parse(url, params, subreddit_name)

    def _search_subreddit(self, subreddit_name: str, query: str) -> list[dict]:
        """Search a single subreddit for housing posts via PullPush API.

        Args:
            subreddit_name: Name of the subreddit (without r/ prefix).
            query: Search query string.

        Returns:
            List of normalized listing dicts from matching posts.
        """
        url = "https://api.pullpush.io/reddit/search/submission/"
        params = {
            "subreddit": subreddit_name,
            "q": query,
            "size": 50,
            "sort": "desc",
            "sort_type": "created_utc",
        }
        return self._fetch_and_parse(url, params, subreddit_name)

    def _fetch_and_parse(
        self, url: str, params: dict, subreddit_name: str
    ) -> list[dict]:
        """Fetch a PullPush API endpoint and parse the posts.

        Args:
            url: PullPush API endpoint URL.
            params: Query parameters.
            subreddit_name: Subreddit name for context.

        Returns:
            List of normalized listing dicts.
        """
        results: list[dict] = []

        # Rate limit: wait between requests
        time.sleep(
            REQUEST_DELAY_MIN
            + (REQUEST_DELAY_MAX - REQUEST_DELAY_MIN) * 0.5
        )

        try:
            response = self.http.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("HTTP error fetching %s", url)
            return results

        try:
            data = response.json()
        except Exception:
            logger.exception("Failed to parse JSON from %s", url)
            return results

        # PullPush returns posts in data[] array (not wrapped in children[])
        posts = data.get("data", [])
        for post_data in posts:
            listing = self._parse_post(post_data, subreddit_name)
            if listing is not None:
                results.append(listing)

        return results

    def _parse_post(self, post: dict, subreddit_name: str) -> dict | None:
        """Parse a Reddit post JSON object into a normalized listing dict.

        Args:
            post: Post data dict from Reddit JSON API.
            subreddit_name: Name of the subreddit the post came from.

        Returns:
            Normalized listing dict, or None if the post is not relevant.
        """
        try:
            title = post.get("title", "")
            body = post.get("selftext", "")
            combined_text = f"{title} {body}"

            # Extract price from title first, then body
            price = _extract_price(title) or _extract_price(body)

            # Filter out posts that are clearly not listings
            housing_keywords = [
                "sublease", "sublet", "rent", "apartment", "room",
                "lease", "housing", "bedroom", "studio", "br", "ba",
                "move in", "move-in", "available", "looking for",
            ]
            has_keyword = any(kw in combined_text.lower() for kw in housing_keywords)
            if not has_keyword and price is None:
                return None

            # Build the source URL
            permalink = post.get("permalink", "")
            source_url = f"https://www.reddit.com{permalink}" if permalink else None

            # Detect listing type
            listing_type = _detect_listing_type(combined_text)

            # Extract contact info from the post
            author = post.get("author")
            contact_info = f"u/{author}" if author else None

            # Parse created timestamp
            created_utc = post.get("created_utc", 0)
            try:
                created_utc = float(created_utc)
            except (TypeError, ValueError):
                created_utc = 0
            created_dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            # Collect image URLs if available
            images: list[str] = []
            preview = post.get("preview")
            if preview:
                try:
                    for img in preview.get("images", []):
                        source_img = img.get("source", {})
                        if source_img.get("url"):
                            images.append(source_img["url"])
                except (AttributeError, TypeError):
                    pass

            post_url = post.get("url", "")
            if post_url and any(
                post_url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif")
            ):
                images.append(post_url)

            post_id = post.get("id", "")

            raw_data = {
                "subreddit": subreddit_name,
                "author": author,
                "created_utc": created_utc,
                "created_dt": created_dt.isoformat(),
                "score": post.get("score", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
                "num_comments": post.get("num_comments", 0),
                "permalink": permalink,
                "selftext": body,
                "url": post_url,
                "flair": post.get("link_flair_text"),
            }

            return self.normalize_listing(
                source="reddit",
                source_id=post_id,
                source_url=source_url,
                title=title,
                description=body if body else None,
                price=price,
                listing_type=listing_type,
                contact_info=contact_info,
                images=images,
                raw_data=raw_data,
            )

        except Exception:
            logger.exception(
                "Error parsing Reddit post %s", post.get("id", "unknown")
            )
            return None

    def close(self) -> None:
        """Close HTTP clients."""
        self.http.close()
        super().close()
