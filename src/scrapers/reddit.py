"""Reddit scraper using PRAW (Python Reddit API Wrapper).

Searches housing-related subreddits for Austin area listings
including subleases, apartments, roommate situations, and lease takeovers.
"""

import logging
import re
from datetime import datetime, timezone

import praw

from src.config import settings
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Subreddits to search for Austin housing posts
SUBREDDITS = ["AustinHousing", "Austin", "UTAustin"]

# Search terms for finding housing-related posts
SEARCH_TERMS = [
    "sublease",
    "apartment",
    "housing",
    "roommate",
    "lease takeover",
    "rent",
]

# Regex to extract price from text (e.g., $1,200, $1200/mo, $950)
PRICE_PATTERN = re.compile(r"\$[\d,]+(?:/mo)?")


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
    """Scraper for Reddit housing posts using PRAW.

    Searches multiple Austin-area subreddits for housing-related posts
    and extracts listing information from post titles and bodies.
    """

    def __init__(self) -> None:
        super().__init__()
        self.reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

    def scrape(self) -> list[dict]:
        """Scrape housing listings from Reddit.

        Iterates through configured subreddits and search terms,
        collecting and normalizing relevant posts.

        Returns:
            List of normalized listing dictionaries.
        """
        listings: list[dict] = []
        seen_ids: set[str] = set()

        for subreddit_name in SUBREDDITS:
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

    def _search_subreddit(self, subreddit_name: str, query: str) -> list[dict]:
        """Search a single subreddit for housing posts.

        Args:
            subreddit_name: Name of the subreddit (without r/ prefix).
            query: Search query string.

        Returns:
            List of normalized listing dicts from matching posts.
        """
        results: list[dict] = []
        subreddit = self.reddit.subreddit(subreddit_name)

        try:
            # Search recent posts (limit to 50 per query to stay within rate limits)
            for post in subreddit.search(query, sort="new", time_filter="week", limit=50):
                listing = self._parse_post(post, subreddit_name)
                if listing is not None:
                    results.append(listing)
        except Exception:
            logger.exception("Failed to search r/%s for '%s'", subreddit_name, query)

        return results

    def _parse_post(self, post, subreddit_name: str) -> dict | None:
        """Parse a Reddit post into a normalized listing dict.

        Args:
            post: PRAW Submission object.
            subreddit_name: Name of the subreddit the post came from.

        Returns:
            Normalized listing dict, or None if the post is not relevant.
        """
        try:
            title = post.title or ""
            body = post.selftext or ""
            combined_text = f"{title} {body}"

            # Extract price from title first, then body
            price = _extract_price(title) or _extract_price(body)

            # Filter out posts that are clearly not listings
            # (e.g., questions about housing market, complaints, etc.)
            # Keep posts that have a price or housing-related keywords
            housing_keywords = [
                "sublease", "sublet", "rent", "apartment", "room",
                "lease", "housing", "bedroom", "studio", "br", "ba",
                "move in", "move-in", "available", "looking for",
            ]
            has_keyword = any(kw in combined_text.lower() for kw in housing_keywords)
            if not has_keyword and price is None:
                return None

            # Build the source URL
            source_url = f"https://www.reddit.com{post.permalink}"

            # Detect listing type
            listing_type = _detect_listing_type(combined_text)

            # Extract contact info from the post
            contact_info = None
            if post.author:
                contact_info = f"u/{post.author.name}"

            # Parse created timestamp
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

            # Collect image URLs if available
            images: list[str] = []
            if hasattr(post, "preview") and post.preview:
                try:
                    for img in post.preview.get("images", []):
                        source_img = img.get("source", {})
                        if source_img.get("url"):
                            images.append(source_img["url"])
                except (AttributeError, TypeError):
                    pass
            if hasattr(post, "url") and post.url and any(
                post.url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif")
            ):
                images.append(post.url)

            raw_data = {
                "subreddit": subreddit_name,
                "author": str(post.author) if post.author else None,
                "created_utc": post.created_utc,
                "created_dt": created_dt.isoformat(),
                "score": post.score,
                "upvote_ratio": post.upvote_ratio,
                "num_comments": post.num_comments,
                "permalink": post.permalink,
                "selftext": body,
                "url": post.url,
                "flair": post.link_flair_text,
            }

            return self.normalize_listing(
                source="reddit",
                source_id=post.id,
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
            logger.exception("Error parsing Reddit post %s", getattr(post, "id", "unknown"))
            return None
