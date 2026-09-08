"""
SentinelVision - Database

Phase 6B: SQLite Persistence Layer

A thin abstraction over the Python standard-library ``sqlite3`` module.

Responsibilities
----------------
- Configurable database path (default ``data/sentinelvision.db``).
- Create the ``data`` directory automatically when missing.
- Per-call connections (no global connections left open forever).
- ``PRAGMA foreign_keys = ON`` on EVERY connection.
- Idempotent schema initialization (safe to call repeatedly).
- Transaction context with rollback on failure.

Security
--------
- All queries use parameterized SQL — never string interpolation.
- No credentials are ever stored or logged.  RTSP URLs are stripped
  of userinfo defensively by the repository layer before persisting.

Timestamps
----------
The database layer stores caller-supplied timestamps verbatim when
given (source PTS timing from the camera pipeline); when absent it
stamps the current UTC time in ISO-8601 format.  It never derives
event timing from FPS.
"""

import datetime
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional, Union

# Default database location (relative to the project root when run from it).
DEFAULT_DB_PATH = os.path.join("data", "sentinelvision.db")

TimestampValue = Union[str, datetime.datetime, float, int, None]


# ---------------------------------------------------------------------------
# Timestamp normalization
# ---------------------------------------------------------------------------
def _to_utc_iso(timestamp: TimestampValue) -> str:
    """Normalize *timestamp* to an ISO-8601 UTC string.

    - ``None``                        -> current UTC time
    - ``datetime.datetime``           -> converted to UTC, ISO format
    - ``float`` / ``int`` (epoch secs) -> converted to UTC ISO format
    - ``str``                          -> stored verbatim (caller-owned,
      e.g. source PTS timing already formatted by the pipeline)
    """
    if timestamp is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.isoformat()

    if isinstance(timestamp, datetime.datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
        return timestamp.astimezone(datetime.timezone.utc).isoformat()

    if isinstance(timestamp, (int, float)):
        dt = datetime.datetime.fromtimestamp(
            float(timestamp), tz=datetime.timezone.utc
        )
        return dt.isoformat()

    return str(timestamp)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS cameras (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        camera_id   TEXT    NOT NULL UNIQUE,
        name        TEXT,
        location    TEXT,
        latitude    REAL,
        longitude   REAL,
        codec       TEXT,
        width       INTEGER,
        height      INTEGER,
        rtsp_url    TEXT,
        webrtc_url  TEXT,
        hls_url     TEXT,
        live        INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT    NOT NULL,
        updated_at  TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vehicle_events (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_vehicle_id INTEGER NOT NULL,
        camera_id            TEXT    NOT NULL,
        timestamp            TEXT    NOT NULL,
        vehicle_class        TEXT    NOT NULL,
        confidence           REAL,
        bbox_x1              REAL,
        bbox_y1              REAL,
        bbox_x2              REAL,
        bbox_y2              REAL,
        direction            TEXT,
        event_type           TEXT    NOT NULL,
        created_at           TEXT    NOT NULL,
        FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS plate_reads (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_vehicle_id INTEGER NOT NULL,
        camera_id            TEXT    NOT NULL,
        normalized_plate     TEXT    NOT NULL,
        raw_ocr              TEXT    NOT NULL,
        ocr_confidence       REAL,
        detector_confidence  REAL,
        combined_confidence  REAL,
        timestamp            TEXT    NOT NULL,
        created_at           TEXT    NOT NULL,
        FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS zone_counts (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        camera_id            TEXT    NOT NULL,
        canonical_vehicle_id INTEGER NOT NULL,
        vehicle_class        TEXT    NOT NULL,
        direction            TEXT    NOT NULL,
        timestamp            TEXT    NOT NULL,
        created_at           TEXT    NOT NULL,
        FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
    )
    """,
    # ------------------------------------------------------------------
    # Phase 7: watchlist + alerts
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS watchlist_entries (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        normalized_plate TEXT    NOT NULL UNIQUE,
        reason           TEXT    NOT NULL,
        category         TEXT    NOT NULL,
        priority         TEXT    NOT NULL,
        notes            TEXT,
        active           INTEGER NOT NULL DEFAULT 1,
        created_at       TEXT    NOT NULL,
        updated_at       TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        watchlist_entry_id   INTEGER NOT NULL,
        normalized_plate     TEXT    NOT NULL,
        canonical_vehicle_id INTEGER NOT NULL,
        camera_id            TEXT    NOT NULL,
        plate_read_id        INTEGER,
        vehicle_class        TEXT,
        confidence           REAL,
        reason               TEXT    NOT NULL,
        category             TEXT    NOT NULL,
        priority             TEXT    NOT NULL,
        timestamp            TEXT    NOT NULL,
        status               TEXT    NOT NULL,
        created_at           TEXT    NOT NULL,
        acknowledged_at      TEXT,
        FOREIGN KEY (watchlist_entry_id) REFERENCES watchlist_entries (id),
        FOREIGN KEY (camera_id)          REFERENCES cameras (camera_id),
        FOREIGN KEY (plate_read_id)      REFERENCES plate_reads (id)
    )
    """,
    # Phase 9.10: global vehicles & cross-camera observations
    """
    CREATE TABLE IF NOT EXISTS global_vehicles (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        global_vehicle_id    TEXT    NOT NULL UNIQUE,
        normalized_plate     TEXT    UNIQUE,
        vehicle_class        TEXT,
        first_seen_at        TEXT    NOT NULL,
        last_seen_at         TEXT    NOT NULL,
        created_at           TEXT    NOT NULL,
        updated_at           TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cross_camera_observations (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        global_vehicle_id    TEXT    NOT NULL,
        camera_id            TEXT    NOT NULL,
        canonical_vehicle_id INTEGER NOT NULL,
        normalized_plate     TEXT,
        vehicle_class        TEXT,
        timestamp            TEXT    NOT NULL,
        plate_read_id        INTEGER,
        created_at           TEXT    NOT NULL,
        FOREIGN KEY (global_vehicle_id) REFERENCES global_vehicles (global_vehicle_id),
        FOREIGN KEY (camera_id)          REFERENCES cameras (camera_id)
    )
    """,
)

# Query-driven indexes (kept minimal).
_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_vehicle_events_camera"
    " ON vehicle_events (camera_id)",
    "CREATE INDEX IF NOT EXISTS idx_vehicle_events_vehicle"
    " ON vehicle_events (canonical_vehicle_id)",
    "CREATE INDEX IF NOT EXISTS idx_vehicle_events_timestamp"
    " ON vehicle_events (timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_plate_reads_plate"
    " ON plate_reads (normalized_plate)",
    "CREATE INDEX IF NOT EXISTS idx_plate_reads_vehicle"
    " ON plate_reads (canonical_vehicle_id)",
    "CREATE INDEX IF NOT EXISTS idx_plate_reads_camera"
    " ON plate_reads (camera_id)",
    "CREATE INDEX IF NOT EXISTS idx_plate_reads_timestamp"
    " ON plate_reads (timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_zone_counts_camera"
    " ON zone_counts (camera_id)",
    "CREATE INDEX IF NOT EXISTS idx_zone_counts_vehicle"
    " ON zone_counts (canonical_vehicle_id)",
    "CREATE INDEX IF NOT EXISTS idx_zone_counts_timestamp"
    " ON zone_counts (timestamp)",
    # Phase 7: watchlist + alerts
    "CREATE INDEX IF NOT EXISTS idx_watchlist_plate"
    " ON watchlist_entries (normalized_plate)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_active"
    " ON watchlist_entries (active)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_category"
    " ON watchlist_entries (category)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_priority"
    " ON watchlist_entries (priority)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_plate"
    " ON alerts (normalized_plate)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_camera"
    " ON alerts (camera_id)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_vehicle"
    " ON alerts (canonical_vehicle_id)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_timestamp"
    " ON alerts (timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_status"
    " ON alerts (status)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_priority"
    " ON alerts (priority)",
    # Phase 9.10: cross-camera indexes
    "CREATE INDEX IF NOT EXISTS idx_global_vehicles_plate"
    " ON global_vehicles (normalized_plate)",
    "CREATE INDEX IF NOT EXISTS idx_cross_camera_obs_gv"
    " ON cross_camera_observations (global_vehicle_id)",
    "CREATE INDEX IF NOT EXISTS idx_cross_camera_obs_camera"
    " ON cross_camera_observations (camera_id)",
    "CREATE INDEX IF NOT EXISTS idx_cross_camera_obs_timestamp"
    " ON cross_camera_observations (timestamp)",
)

# Reasonable duplicate protection.  The Phase 4 / Phase 5 modules keep
# their own in-memory duplicate protection; these unique indexes simply
# make accidental re-inserts harmless (repositories use INSERT OR IGNORE).
_UNIQUE_STATEMENTS = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_plate_reads_read"
    " ON plate_reads (canonical_vehicle_id, camera_id, normalized_plate)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_zone_counts_count"
    " ON zone_counts (camera_id, canonical_vehicle_id, direction, vehicle_class)",
)

# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------
class Database:
    """SQLite database abstraction for SentinelVision.

    Usage
    -----
    ::

        db = Database()          # default: data/sentinelvision.db
        db.initialize()

        with db.connection() as conn:
            conn.execute("SELECT ...")
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path) if db_path is not None else DEFAULT_DB_PATH

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        """Open a new connection with foreign keys enabled.

        Row access uses ``sqlite3.Row`` for name-based lookups.  The
        caller is responsible for closing the connection (or prefer
        the :meth:`connection` context manager).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection; commit on success, rollback and re-raise
        on failure, always close."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Schema initialization
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        """Create the data directory (if needed) and all tables/indexes.

        Idempotent: safe to call any number of times.
        """
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)

        with self.connection() as conn:
            for statement in _SCHEMA_STATEMENTS + _INDEX_STATEMENTS + _UNIQUE_STATEMENTS:
                conn.execute(statement)

    # ------------------------------------------------------------------
    # Introspection helpers (used by tests / diagnostics)
    # ------------------------------------------------------------------
    def table_names(self):
        """Return the sorted list of user tables in the database."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return sorted(r["name"] for r in rows)

    def foreign_keys_enabled(self, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Report whether ``PRAGMA foreign_keys`` is ON (per connection)."""
        if conn is not None:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            return bool(row[0])
        with self.connection() as c:
            row = c.execute("PRAGMA foreign_keys").fetchone()
            return bool(row[0])



