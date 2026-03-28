#!/usr/bin/env python3
"""Score all unscored listings in the database."""

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
    """Load unscored listings, compute deal scores, and save them."""
    from src.database.connection import AsyncSessionLocal
    from src.database.crud import get_unscored_listings, update_listing_scores
    from src.scoring.deal_scorer import calculate_deal_score, classify_deal

    async with AsyncSessionLocal() as session:
        listings = await get_unscored_listings(session)
        logger.info("Found %d unscored listings", len(listings))

        if not listings:
            logger.info("All listings are already scored. Nothing to do.")
            return

        scored = 0
        errors = 0

        for listing in listings:
            try:
                deal_score = calculate_deal_score(listing)
                classification = classify_deal(deal_score)

                await update_listing_scores(
                    session,
                    listing.id,
                    {
                        "deal_score": deal_score,
                        "deal_classification": classification,
                    },
                )
                scored += 1
                logger.info(
                    "Scored: %s | Score: %d | Class: %s | Price: %s",
                    listing.title or listing.source_id,
                    deal_score,
                    classification,
                    listing.price,
                )
            except Exception:
                errors += 1
                logger.exception("Error scoring listing %s", listing.id)

        logger.info(
            "Scoring complete. %d scored, %d errors, %d total.",
            scored,
            errors,
            len(listings),
        )


if __name__ == "__main__":
    asyncio.run(main())
