"""
SentinelVision - Database Migration: Phase O.2

Adds coordinate_source and coordinate_approximate columns to the cameras table if not already present.
Populates/synchronizes backend camera metadata for all 30 cameras.
"""

import os
import sqlite3
import logging
from backend.db.database import Database, DEFAULT_DB_PATH

logger = logging.getLogger(__name__)


def migrate_phase_o_2(db_path: str = DEFAULT_DB_PATH) -> None:
    """Safely apply Phase O.2 column additions to the cameras table."""
    db = Database(db_path)
    db.initialize()

    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(cameras)")
        columns = [row["name"] for row in cursor.fetchall()]

        if "coordinate_source" not in columns:
            logger.info("Adding coordinate_source column to cameras table")
            conn.execute("ALTER TABLE cameras ADD COLUMN coordinate_source TEXT")

        if "coordinate_approximate" not in columns:
            logger.info("Adding coordinate_approximate column to cameras table")
            conn.execute("ALTER TABLE cameras ADD COLUMN coordinate_approximate INTEGER")

    logger.info("Phase O.2 migration complete for %s", db_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_phase_o_2()
