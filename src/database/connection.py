"""Database connection setup for async and sync engines."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings

# Async engine (for FastAPI / main app)
async_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# Sync engine (for Alembic migrations and scripts)
sync_engine = create_engine(settings.database_url_sync, echo=False)
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


async def get_async_session() -> AsyncSession:
    """Dependency for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session() -> Session:
    """Get a synchronous session for scripts."""
    with SyncSessionLocal() as session:
        yield session
