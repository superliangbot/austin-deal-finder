"""SQLAlchemy ORM models."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    estimated_total: Mapped[float | None] = mapped_column(Numeric(10, 2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[float | None] = mapped_column(Numeric(3, 1))
    sqft: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    distance_miles: Mapped[float | None] = mapped_column(Numeric(5, 2))
    walk_minutes: Mapped[int | None] = mapped_column(Integer)
    listing_type: Mapped[str | None] = mapped_column(String(50))
    furnished: Mapped[bool | None] = mapped_column(Boolean)
    pets_allowed: Mapped[bool | None] = mapped_column(Boolean)
    available_date: Mapped[date | None] = mapped_column(Date)
    contact_info: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    raw_data: Mapped[dict | None] = mapped_column(JSONB)

    # LLM enrichment fields
    summary: Mapped[str | None] = mapped_column(Text)
    urgency_score: Mapped[int | None] = mapped_column(Integer)
    negotiability_score: Mapped[int | None] = mapped_column(Integer)
    incentives: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    deal_classification: Mapped[str | None] = mapped_column(String(20))
    outreach_suggestion: Mapped[str | None] = mapped_column(Text)

    # Scoring
    deal_score: Mapped[int | None] = mapped_column(Integer)

    # Meta
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    price_history: Mapped[dict | None] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_source_source_id"),
        Index("idx_listings_deal_score", deal_score.desc()),
        Index("idx_listings_source", "source"),
        Index("idx_listings_price", "price"),
        Index("idx_listings_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Listing {self.source}:{self.source_id} ${self.price} — {self.title!r}>"
