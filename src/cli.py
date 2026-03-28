"""CLI entry point for Austin Deal Finder using Click."""

import asyncio
import logging
import sys

import click

# Configure logging for CLI usage
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine in a new event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@click.group()
def cli():
    """Austin Deal Finder -- find the best housing deals near downtown Austin."""
    pass


@cli.command()
def scrape():
    """Run all scrapers and save results to the database."""

    async def _scrape():
        from src.database.connection import AsyncSessionLocal
        from src.database.crud import upsert_listing
        from src.enrichment.geocoder import enrich_listing_location

        # Import available scrapers
        scrapers = []
        try:
            from src.scrapers.craigslist import CraigslistScraper
            scrapers.append(("Craigslist", CraigslistScraper))
        except ImportError:
            logger.warning("Craigslist scraper not available")

        try:
            from src.scrapers.reddit import RedditScraper
            scrapers.append(("Reddit", RedditScraper))
        except ImportError:
            logger.warning("Reddit scraper not available")

        total_saved = 0

        for name, scraper_cls in scrapers:
            logger.info("Running %s scraper...", name)
            try:
                with scraper_cls() as scraper:
                    listings = scraper.scrape()
                    logger.info("%s scraper returned %d listings", name, len(listings))

                    async with AsyncSessionLocal() as session:
                        for listing_data in listings:
                            try:
                                # Enrich with location data
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

        logger.info("Scraping complete. %d listings saved to database.", total_saved)

    _run_async(_scrape())


@cli.command()
def score():
    """Score all unscored listings in the database."""

    async def _score():
        from src.database.connection import AsyncSessionLocal
        from src.database.crud import get_unscored_listings, update_listing_scores
        from src.scoring.deal_scorer import calculate_deal_score, classify_deal

        async with AsyncSessionLocal() as session:
            listings = await get_unscored_listings(session)
            logger.info("Found %d unscored listings", len(listings))

            scored = 0
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
                    logger.debug(
                        "Scored listing %s: %d (%s)",
                        listing.id,
                        deal_score,
                        classification,
                    )
                except Exception:
                    logger.exception("Error scoring listing %s", listing.id)

            logger.info("Scoring complete. %d/%d listings scored.", scored, len(listings))

    _run_async(_score())


@cli.command()
def enrich():
    """Run LLM enrichment on unenriched listings."""

    async def _enrich():
        from sqlalchemy import select

        from src.database.connection import AsyncSessionLocal
        from src.database.crud import update_listing_enrichment
        from src.database.models import Listing

        async with AsyncSessionLocal() as session:
            # Find listings that need enrichment (no summary yet)
            stmt = select(Listing).where(
                Listing.is_active.is_(True),
                Listing.summary.is_(None),
            )
            result = await session.execute(stmt)
            listings = list(result.scalars().all())
            logger.info("Found %d listings needing enrichment", len(listings))

            if not listings:
                logger.info("No listings need enrichment.")
                return

            # Try to import the LLM enricher
            try:
                from src.enrichment.llm_enricher import enrich_listing
            except ImportError:
                logger.error(
                    "LLM enricher module not available. "
                    "Create src/enrichment/llm_enricher.py with an enrich_listing() function."
                )
                return

            enriched_count = 0
            for listing in listings:
                try:
                    enrichment_data = await enrich_listing(listing)
                    if enrichment_data:
                        await update_listing_enrichment(
                            session, listing.id, enrichment_data
                        )
                        enriched_count += 1
                        logger.info("Enriched listing: %s", listing.title)
                except Exception:
                    logger.exception("Error enriching listing %s", listing.id)

            logger.info(
                "Enrichment complete. %d/%d listings enriched.",
                enriched_count,
                len(listings),
            )

    _run_async(_enrich())


@cli.command()
def notify():
    """Send Telegram alerts for high-score unnotified deals."""

    async def _notify():
        from src.database.connection import AsyncSessionLocal
        from src.database.crud import get_unnotified_deals, mark_notified
        from src.notifications.telegram import send_batch_alerts

        async with AsyncSessionLocal() as session:
            deals = await get_unnotified_deals(session, min_score=65)
            logger.info("Found %d unnotified deals to alert on", len(deals))

            if not deals:
                logger.info("No new deals to notify about.")
                return

            sent_count = await send_batch_alerts(deals)

            # Mark successfully notified listings
            if sent_count > 0:
                notified_ids = [deal.id for deal in deals[:sent_count]]
                await mark_notified(session, notified_ids)
                logger.info("Marked %d listings as notified", sent_count)

            logger.info(
                "Notification complete. %d/%d alerts sent.", sent_count, len(deals)
            )

    _run_async(_notify())


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload")
def dashboard(host, port, reload):
    """Start the FastAPI dashboard server."""
    import uvicorn

    logger.info("Starting dashboard server at http://%s:%d", host, port)
    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@cli.command(name="run-all")
def run_all():
    """Run scrape, enrich, score, and notify in sequence."""

    async def _run_all():
        from src.database.connection import AsyncSessionLocal
        from src.database.crud import (
            get_unnotified_deals,
            get_unscored_listings,
            mark_notified,
            update_listing_scores,
            upsert_listing,
        )
        from src.enrichment.geocoder import enrich_listing_location
        from src.notifications.telegram import send_batch_alerts
        from src.scoring.deal_scorer import calculate_deal_score, classify_deal

        # ── Step 1: Scrape ──────────────────────────────────────────────
        logger.info("=== Step 1/4: Scraping ===")
        scrapers = []
        try:
            from src.scrapers.craigslist import CraigslistScraper
            scrapers.append(("Craigslist", CraigslistScraper))
        except ImportError:
            logger.warning("Craigslist scraper not available")
        try:
            from src.scrapers.reddit import RedditScraper
            scrapers.append(("Reddit", RedditScraper))
        except ImportError:
            logger.warning("Reddit scraper not available")

        total_saved = 0
        for name, scraper_cls in scrapers:
            logger.info("Running %s scraper...", name)
            try:
                with scraper_cls() as scraper:
                    listings = scraper.scrape()
                    logger.info("%s: %d listings found", name, len(listings))
                    async with AsyncSessionLocal() as session:
                        for listing_data in listings:
                            try:
                                enriched = enrich_listing_location(listing_data)
                                listing_data["latitude"] = enriched.get("lat")
                                listing_data["longitude"] = enriched.get("lon")
                                listing_data["distance_miles"] = enriched.get("distance_miles")
                                listing_data["walk_minutes"] = enriched.get("walk_minutes")
                                await upsert_listing(session, listing_data)
                                total_saved += 1
                            except Exception:
                                logger.exception("Error saving listing")
            except Exception:
                logger.exception("Error running %s scraper", name)

        logger.info("Scraping complete: %d listings saved", total_saved)

        # ── Step 2: Enrich ──────────────────────────────────────────────
        logger.info("=== Step 2/4: Enrichment ===")
        try:
            from sqlalchemy import select

            from src.database.crud import update_listing_enrichment
            from src.database.models import Listing

            async with AsyncSessionLocal() as session:
                stmt = select(Listing).where(
                    Listing.is_active.is_(True),
                    Listing.summary.is_(None),
                )
                result = await session.execute(stmt)
                unenriched = list(result.scalars().all())
                logger.info("Found %d listings needing enrichment", len(unenriched))

                try:
                    from src.enrichment.llm_enricher import enrich_listing

                    enriched_count = 0
                    for listing in unenriched:
                        try:
                            enrichment_data = await enrich_listing(listing)
                            if enrichment_data:
                                await update_listing_enrichment(
                                    session, listing.id, enrichment_data
                                )
                                enriched_count += 1
                        except Exception:
                            logger.exception("Error enriching listing %s", listing.id)
                    logger.info("Enrichment complete: %d enriched", enriched_count)
                except ImportError:
                    logger.warning("LLM enricher not available, skipping enrichment")
        except Exception:
            logger.exception("Error during enrichment step")

        # ── Step 3: Score ───────────────────────────────────────────────
        logger.info("=== Step 3/4: Scoring ===")
        async with AsyncSessionLocal() as session:
            unscored = await get_unscored_listings(session)
            logger.info("Found %d unscored listings", len(unscored))
            scored = 0
            for listing in unscored:
                try:
                    deal_score = calculate_deal_score(listing)
                    classification = classify_deal(deal_score)
                    await update_listing_scores(
                        session,
                        listing.id,
                        {"deal_score": deal_score, "deal_classification": classification},
                    )
                    scored += 1
                except Exception:
                    logger.exception("Error scoring listing %s", listing.id)
            logger.info("Scoring complete: %d scored", scored)

        # ── Step 4: Notify ──────────────────────────────────────────────
        logger.info("=== Step 4/4: Notifications ===")
        async with AsyncSessionLocal() as session:
            deals = await get_unnotified_deals(session, min_score=65)
            logger.info("Found %d unnotified deals", len(deals))
            if deals:
                sent = await send_batch_alerts(deals)
                if sent > 0:
                    notified_ids = [d.id for d in deals[:sent]]
                    await mark_notified(session, notified_ids)
                logger.info("Notifications sent: %d/%d", sent, len(deals))
            else:
                logger.info("No new deals to notify about.")

        logger.info("=== All steps complete ===")

    _run_async(_run_all())


if __name__ == "__main__":
    cli()
