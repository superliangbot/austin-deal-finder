#!/usr/bin/env python3
"""One-shot scrape script -- runs all scrapers and saves results to the database."""

import asyncio
import logging
import sys

# Ensure the project root is on the path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    """Run all available scrapers and save results to the database."""
    from src.database.connection import AsyncSessionLocal
    from src.database.crud import upsert_listing
    from src.enrichment.geocoder import enrich_listing_location

    # Collect available scrapers
    scrapers = []

    try:
        from src.scrapers.craigslist import CraigslistScraper
        scrapers.append(("Craigslist", CraigslistScraper))
    except ImportError:
        logger.warning("Craigslist scraper not available (missing dependencies?)")

    try:
        from src.scrapers.reddit import RedditScraper
        scrapers.append(("Reddit", RedditScraper))
    except ImportError:
        logger.warning("Reddit scraper not available (missing dependencies?)")

    if not scrapers:
        logger.error("No scrapers available. Exiting.")
        return

    total_saved = 0

    for name, scraper_cls in scrapers:
        logger.info("--- Running %s scraper ---", name)
        try:
            with scraper_cls() as scraper:
                listings = scraper.scrape()
                logger.info("%s scraper returned %d listings", name, len(listings))

                async with AsyncSessionLocal() as session:
                    for listing_data in listings:
                        try:
                            # Enrich with geocoding / distance info
                            enriched = enrich_listing_location(listing_data)
                            listing_data["latitude"] = enriched.get("lat")
                            listing_data["longitude"] = enriched.get("lon")
                            listing_data["distance_miles"] = enriched.get("distance_miles")
                            listing_data["walk_minutes"] = enriched.get("walk_minutes")

                            await upsert_listing(session, listing_data)
                            total_saved += 1
                        except Exception:
                            logger.exception(
                                "Error saving listing: %s",
                                listing_data.get("title", "unknown"),
                            )
        except Exception:
            logger.exception("Error running %s scraper", name)

    logger.info("Scraping complete. %d total listings saved to database.", total_saved)


if __name__ == "__main__":
    asyncio.run(main())
