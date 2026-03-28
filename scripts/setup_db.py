#!/usr/bin/env python3
"""Initialize the database by creating all tables defined in SQLAlchemy models.

This script uses the synchronous engine to create tables directly.
For production migrations, use Alembic instead.
"""

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


def main():
    """Create all database tables from SQLAlchemy models."""
    try:
        from src.database.connection import sync_engine
        from src.database.models import Base

        logger.info("Creating database tables...")
        logger.info("Database URL: %s", str(sync_engine.url))

        Base.metadata.create_all(bind=sync_engine)

        logger.info("Database tables created successfully.")

        # Log the tables that were created
        for table_name in Base.metadata.tables:
            logger.info("  - Table: %s", table_name)

    except Exception:
        logger.exception("Failed to create database tables")
        sys.exit(1)


if __name__ == "__main__":
    main()
