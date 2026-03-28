"""CRUD operations for listings."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Listing


async def upsert_listing(session: AsyncSession, data: dict) -> Listing:
    """Insert or update a listing using (source, source_id) as the conflict key.

    If the listing already exists and the price changed, append to price_history.
    """
    stmt = pg_insert(Listing).values(**data)

    # On conflict, update mutable fields and track price changes
    update_cols = {
        "title": stmt.excluded.title,
        "description": stmt.excluded.description,
        "price": stmt.excluded.price,
        "source_url": stmt.excluded.source_url,
        "last_seen_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
        "raw_data": stmt.excluded.raw_data,
    }

    stmt = stmt.on_conflict_do_update(
        constraint="uq_source_source_id",
        set_=update_cols,
    ).returning(Listing)

    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def get_listing_by_id(session: AsyncSession, listing_id: UUID) -> Listing | None:
    result = await session.execute(select(Listing).where(Listing.id == listing_id))
    return result.scalar_one_or_none()


async def get_active_listings(
    session: AsyncSession,
    max_price: float | None = None,
    source: str | None = None,
    min_score: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Listing]:
    """Fetch active listings with optional filters, ordered by deal score."""
    stmt = select(Listing).where(Listing.is_active.is_(True))

    if max_price is not None:
        stmt = stmt.where(Listing.price <= max_price)
    if source is not None:
        stmt = stmt.where(Listing.source == source)
    if min_score is not None:
        stmt = stmt.where(Listing.deal_score >= min_score)

    stmt = stmt.order_by(Listing.deal_score.desc().nulls_last()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_unscored_listings(session: AsyncSession) -> list[Listing]:
    """Get listings that haven't been scored yet."""
    stmt = (
        select(Listing)
        .where(Listing.is_active.is_(True), Listing.deal_score.is_(None))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_unnotified_deals(
    session: AsyncSession, min_score: int = 65
) -> list[Listing]:
    """Get high-score listings that haven't been notified yet."""
    stmt = (
        select(Listing)
        .where(
            Listing.is_active.is_(True),
            Listing.notified.is_(False),
            Listing.deal_score >= min_score,
        )
        .order_by(Listing.deal_score.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_notified(session: AsyncSession, listing_ids: list[UUID]) -> None:
    """Mark listings as notified."""
    stmt = (
        update(Listing)
        .where(Listing.id.in_(listing_ids))
        .values(notified=True, updated_at=datetime.utcnow())
    )
    await session.execute(stmt)
    await session.commit()


async def update_listing_scores(
    session: AsyncSession, listing_id: UUID, scores: dict
) -> None:
    """Update scoring and enrichment fields for a listing."""
    stmt = (
        update(Listing)
        .where(Listing.id == listing_id)
        .values(**scores, updated_at=datetime.utcnow())
    )
    await session.execute(stmt)
    await session.commit()


async def update_listing_enrichment(
    session: AsyncSession, listing_id: UUID, enrichment: dict
) -> None:
    """Update LLM enrichment fields for a listing."""
    stmt = (
        update(Listing)
        .where(Listing.id == listing_id)
        .values(**enrichment, updated_at=datetime.utcnow())
    )
    await session.execute(stmt)
    await session.commit()


async def append_price_history(
    session: AsyncSession, listing: Listing, new_price: float
) -> None:
    """Append a price change to the listing's price history."""
    history = listing.price_history or []
    history.append({
        "price": float(new_price),
        "seen_at": datetime.utcnow().isoformat(),
    })
    stmt = (
        update(Listing)
        .where(Listing.id == listing.id)
        .values(price_history=history, updated_at=datetime.utcnow())
    )
    await session.execute(stmt)
    await session.commit()


async def get_listing_stats(session: AsyncSession) -> dict:
    """Get summary statistics for the dashboard."""
    from sqlalchemy import func

    total = await session.execute(
        select(func.count()).select_from(Listing).where(Listing.is_active.is_(True))
    )
    avg_price = await session.execute(
        select(func.avg(Listing.price)).where(Listing.is_active.is_(True))
    )
    avg_score = await session.execute(
        select(func.avg(Listing.deal_score)).where(
            Listing.is_active.is_(True), Listing.deal_score.is_not(None)
        )
    )
    steals = await session.execute(
        select(func.count())
        .select_from(Listing)
        .where(Listing.is_active.is_(True), Listing.deal_score >= 80)
    )

    return {
        "total_active": total.scalar() or 0,
        "avg_price": round(float(avg_price.scalar() or 0), 2),
        "avg_score": round(float(avg_score.scalar() or 0), 1),
        "steals_count": steals.scalar() or 0,
    }
