"""FastAPI dashboard API for Austin Deal Finder."""

import logging
import os
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_async_session
from src.database.crud import (
    get_active_listings,
    get_listing_by_id,
    get_listing_stats,
    upsert_listing,
)
from src.database.models import Listing
from src.scoring.deal_scorer import calculate_deal_score, classify_deal

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Austin Deal Finder",
    description="Housing deal-finding dashboard for downtown Austin",
    version="1.0.0",
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates directory (relative to project root)
_templates_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
templates = Jinja2Templates(directory=os.path.abspath(_templates_dir))


# ── Pydantic schemas ─────────────────────────────────────────────────────────


class ManualListingInput(BaseModel):
    """Schema for manually adding a listing (e.g., from Facebook)."""

    title: str
    description: str | None = None
    price: float | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    address: str | None = None
    listing_type: str | None = None
    furnished: bool | None = None
    pets_allowed: bool | None = None
    available_date: str | None = None
    contact_info: str | None = None
    source_url: str | None = None


class ListingResponse(BaseModel):
    """JSON response for a single listing."""

    id: str
    source: str
    source_id: str | None
    source_url: str | None
    title: str | None
    description: str | None
    price: float | None
    estimated_total: float | None
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    address: str | None
    distance_miles: float | None
    walk_minutes: int | None
    listing_type: str | None
    furnished: bool | None
    pets_allowed: bool | None
    available_date: str | None
    contact_info: str | None
    summary: str | None
    urgency_score: int | None
    incentives: list[str] | None
    deal_classification: str | None
    outreach_suggestion: str | None
    deal_score: int | None
    is_active: bool
    notified: bool
    first_seen_at: str | None
    created_at: str | None

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    """JSON response for dashboard statistics."""

    total_active: int
    avg_price: float
    avg_score: float
    steals_count: int


# ── Helper ────────────────────────────────────────────────────────────────────


def _listing_to_dict(listing: Listing) -> dict:
    """Convert a Listing ORM object to a JSON-serializable dict."""
    return {
        "id": str(listing.id),
        "source": listing.source,
        "source_id": listing.source_id,
        "source_url": listing.source_url,
        "title": listing.title,
        "description": listing.description,
        "price": float(listing.price) if listing.price is not None else None,
        "estimated_total": float(listing.estimated_total) if listing.estimated_total is not None else None,
        "bedrooms": listing.bedrooms,
        "bathrooms": float(listing.bathrooms) if listing.bathrooms is not None else None,
        "sqft": listing.sqft,
        "address": listing.address,
        "distance_miles": float(listing.distance_miles) if listing.distance_miles is not None else None,
        "walk_minutes": listing.walk_minutes,
        "listing_type": listing.listing_type,
        "furnished": listing.furnished,
        "pets_allowed": listing.pets_allowed,
        "available_date": listing.available_date.isoformat() if listing.available_date else None,
        "contact_info": listing.contact_info,
        "summary": listing.summary,
        "urgency_score": listing.urgency_score,
        "incentives": listing.incentives,
        "deal_classification": listing.deal_classification,
        "outreach_suggestion": listing.outreach_suggestion,
        "deal_score": listing.deal_score,
        "is_active": listing.is_active,
        "notified": listing.notified,
        "first_seen_at": listing.first_seen_at.isoformat() if listing.first_seen_at else None,
        "created_at": listing.created_at.isoformat() if listing.created_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the HTML dashboard page."""
    try:
        return templates.TemplateResponse("dashboard.html", {"request": request})
    except Exception as exc:
        logger.error("Error rendering dashboard template: %s", exc)
        return HTMLResponse(
            content="<h1>Austin Deal Finder</h1><p>Dashboard template not found. "
                    "Place a dashboard.html in the templates/ directory.</p>",
            status_code=200,
        )


@app.get("/api/listings", response_model=list[ListingResponse])
async def list_listings(
    max_price: float | None = Query(None, description="Maximum monthly rent"),
    source: str | None = Query(None, description="Filter by source (reddit, craigslist, etc.)"),
    min_score: int | None = Query(None, description="Minimum deal score (0-100)"),
    limit: int = Query(100, ge=1, le=500, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_async_session),
):
    """Return active listings with optional filters, ordered by deal score."""
    try:
        listings = await get_active_listings(
            session,
            max_price=max_price,
            source=source,
            min_score=min_score,
            limit=limit,
            offset=offset,
        )
        return [_listing_to_dict(listing) for listing in listings]
    except Exception as exc:
        logger.error("Error fetching listings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch listings")


@app.get("/api/listings/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Return a single listing by UUID."""
    try:
        listing = await get_listing_by_id(session, listing_id)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")
        return _listing_to_dict(listing)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching listing %s: %s", listing_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch listing")


@app.get("/api/stats", response_model=StatsResponse)
async def stats(
    session: AsyncSession = Depends(get_async_session),
):
    """Return dashboard statistics for active listings."""
    try:
        stats_data = await get_listing_stats(session)
        return stats_data
    except Exception as exc:
        logger.error("Error fetching stats: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


@app.post("/api/listings/manual", response_model=ListingResponse)
async def add_manual_listing(
    data: ManualListingInput,
    session: AsyncSession = Depends(get_async_session),
):
    """Manually add a listing (e.g., from Facebook groups).

    The listing is scored automatically after insertion.
    """
    try:
        # Build listing data dict for upsert
        import uuid

        source_id = f"manual-{uuid.uuid4().hex[:12]}"

        listing_data = {
            "source": "manual",
            "source_id": source_id,
            "source_url": data.source_url,
            "title": data.title,
            "description": data.description,
            "price": data.price,
            "bedrooms": data.bedrooms,
            "bathrooms": data.bathrooms,
            "sqft": data.sqft,
            "address": data.address,
            "listing_type": data.listing_type,
            "furnished": data.furnished,
            "pets_allowed": data.pets_allowed,
            "contact_info": data.contact_info,
            "raw_data": {"manual_input": True},
        }

        # Parse available_date if provided
        if data.available_date:
            try:
                from datetime import date

                listing_data["available_date"] = date.fromisoformat(data.available_date)
            except ValueError:
                logger.warning("Invalid available_date format: %s", data.available_date)

        # Enrich with location data if address is provided
        if data.address:
            try:
                from src.enrichment.geocoder import enrich_listing_location

                enriched = enrich_listing_location(listing_data)
                listing_data["latitude"] = enriched.get("lat")
                listing_data["longitude"] = enriched.get("lon")
                listing_data["distance_miles"] = enriched.get("distance_miles")
                listing_data["walk_minutes"] = enriched.get("walk_minutes")
            except Exception as exc:
                logger.warning("Failed to enrich location for manual listing: %s", exc)

        # Score the listing
        score = calculate_deal_score(listing_data)
        classification = classify_deal(score)
        listing_data["deal_score"] = score
        listing_data["deal_classification"] = classification

        listing = await upsert_listing(session, listing_data)
        return _listing_to_dict(listing)

    except Exception as exc:
        logger.error("Error adding manual listing: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add listing")
