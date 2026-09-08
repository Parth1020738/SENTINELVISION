"""
SentinelVision - Repositories

Phase 6B: SQLite Persistence Layer

Repository classes for cameras, vehicle events, plate reads, and zone
counts.  ALL SQL lives here (or in ``database.py``) — AI modules never
write SQL.

Security
--------
- Parameterized queries only — no string interpolation of values.
- RTSP URLs are stripped of userinfo (``user:pass@``) defensively
  before being persisted.  Credentials are never stored or logged.

Plate normalization
-------------------
This layer REUSES ``backend.ai.plate_ocr.normalize_plate_text``; no
competing normalization is implemented here.

Duplicate protection
--------------------
Phase 4 (zone counter) and Phase 5 (ANPR engine) already implement
their own in-memory duplicate protection.  This layer adds light
``INSERT OR IGNORE`` protection backed by unique indexes so accidental
re-inserts are harmless without changing AI behavior.
"""

import sqlite3
from typing import List, Optional

from backend.db.database import Database, _to_utc_iso
from backend.db.models import (
    ALERT_STATUSES,
    CAMERA_HEALTH_STATUSES,
    WATCHLIST_CATEGORIES,
    WATCHLIST_PRIORITIES,
    Alert,
    Camera,
    CameraHealth,
    AuditLog,
    CrossCameraObservation,
    GlobalVehicle,
    PlateRead,
    VehicleEvent,
    WatchlistEntry,
    ZoneCount,
)
from backend.ai.plate_ocr import normalize_plate_text
from backend.camera.rtsp_credentials import redact_url


def _row_to_camera(row: sqlite3.Row) -> Camera:
    return Camera(
        camera_id=row["camera_id"],
        name=row["name"],
        location=row["location"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        codec=row["codec"],
        width=row["width"],
        height=row["height"],
        rtsp_url=row["rtsp_url"],
        webrtc_url=row["webrtc_url"],
        hls_url=row["hls_url"],
        live=bool(row["live"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

# ---------------------------------------------------------------------------
# Camera repository
# ---------------------------------------------------------------------------
class CameraRepository:
    """Upsert / lookup / status updates for the camera catalogue.

    ``camera_id`` is the stable identity: upserting an existing camera
    updates its metadata in place without creating duplicate rows.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_camera(self, camera: Camera) -> int:
        """Insert or update a camera record.

        RTSP URLs are stripped of credentials before persistence.
        Returns the database row id.
        """
        now = _to_utc_iso(None)
        safe_rtsp = redact_url(camera.rtsp_url) if camera.rtsp_url else camera.rtsp_url
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO cameras (
                    camera_id, name, location, latitude, longitude,
                    codec, width, height,
                    rtsp_url, webrtc_url, hls_url, live,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (camera_id) DO UPDATE SET
                    name       = excluded.name,
                    location   = excluded.location,
                    latitude   = excluded.latitude,
                    longitude  = excluded.longitude,
                    codec      = excluded.codec,
                    width      = excluded.width,
                    height     = excluded.height,
                    rtsp_url   = excluded.rtsp_url,
                    webrtc_url = excluded.webrtc_url,
                    hls_url    = excluded.hls_url,
                    live       = excluded.live,
                    updated_at = excluded.updated_at
                """,
                (
                    camera.camera_id, camera.name, camera.location,
                    camera.latitude, camera.longitude,
                    camera.codec, camera.width, camera.height,
                    safe_rtsp, camera.webrtc_url, camera.hls_url,
                    1 if camera.live else 0,
                    now, now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM cameras WHERE camera_id = ?",
                (camera.camera_id,),
            ).fetchone()
            return int(row["id"])

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        """Return the camera with *camera_id*, or ``None``."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cameras WHERE camera_id = ?",
                (camera_id,),
            ).fetchone()
        return _row_to_camera(row) if row else None

    def list_cameras(self) -> List[Camera]:
        """Return all cameras ordered by camera_id."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cameras ORDER BY camera_id"
            ).fetchall()
        return [_row_to_camera(r) for r in rows]

    def update_camera_status(self, camera_id: str, live: bool) -> bool:
        """Set the live status of a camera.  Returns True if found."""
        with self.db.connection() as conn:
            cur = conn.execute(
                "UPDATE cameras SET live = ?, updated_at = ?"
                " WHERE camera_id = ?",
                (1 if live else 0, _to_utc_iso(None), camera_id),
            )
        return cur.rowcount > 0

# ---------------------------------------------------------------------------
# Vehicle event repository
# ---------------------------------------------------------------------------
class VehicleRepository:
    """Insertion and history queries for meaningful vehicle events.

    One row per EVENT (DETECTED / ZONE_IN / ZONE_OUT / TRACK_END) —
    never one row per video frame.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_vehicle_event(self, event: VehicleEvent) -> int:
        """Insert one vehicle event.  Returns the new row id."""
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO vehicle_events (
                    canonical_vehicle_id, camera_id, timestamp,
                    vehicle_class, confidence,
                    bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                    direction, event_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.canonical_vehicle_id,
                    event.camera_id,
                    _to_utc_iso(event.timestamp),
                    event.vehicle_class,
                    event.confidence,
                    event.bbox_x1, event.bbox_y1,
                    event.bbox_x2, event.bbox_y2,
                    event.direction,
                    event.event_type,
                    _to_utc_iso(None),
                ),
            )
        return int(cur.lastrowid)

    def get_vehicle_history(
        self, canonical_vehicle_id: int
    ) -> List[VehicleEvent]:
        """All events for one canonical vehicle, oldest first."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM vehicle_events"
                " WHERE canonical_vehicle_id = ?"
                " ORDER BY timestamp",
                (canonical_vehicle_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def get_vehicle_events_by_camera(self, camera_id: str) -> List[VehicleEvent]:
        """All events for one camera, oldest first."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM vehicle_events WHERE camera_id = ?"
                " ORDER BY timestamp",
                (camera_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def get_recent_vehicle_events(
        self, limit: int = 100
    ) -> List[VehicleEvent]:
        """Most recent events across all cameras (newest first)."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM vehicle_events"
                " ORDER BY timestamp DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_row_to_event(r) for r in rows]


def _row_to_event(row: sqlite3.Row) -> VehicleEvent:
    return VehicleEvent(
        id=row["id"],
        canonical_vehicle_id=row["canonical_vehicle_id"],
        camera_id=row["camera_id"],
        timestamp=row["timestamp"],
        vehicle_class=row["vehicle_class"],
        confidence=row["confidence"],
        bbox_x1=row["bbox_x1"], bbox_y1=row["bbox_y1"],
        bbox_x2=row["bbox_x2"], bbox_y2=row["bbox_y2"],
        direction=row["direction"],
        event_type=row["event_type"],
        created_at=row["created_at"],
    )

# ---------------------------------------------------------------------------
# Plate read repository
# ---------------------------------------------------------------------------
def _row_to_plate(row: sqlite3.Row) -> PlateRead:
    return PlateRead(
        id=row["id"],
        canonical_vehicle_id=row["canonical_vehicle_id"],
        camera_id=row["camera_id"],
        normalized_plate=row["normalized_plate"],
        raw_ocr=row["raw_ocr"],
        ocr_confidence=row["ocr_confidence"],
        detector_confidence=row["detector_confidence"],
        combined_confidence=row["combined_confidence"],
        timestamp=row["timestamp"],
        created_at=row["created_at"],
    )


class PlateRepository:
    """Storage and search for aggregated plate reads.

    All searches operate on NORMALIZED plates via
    ``backend.ai.plate_ocr.normalize_plate_text`` (reused, not
    re-implemented).  E.g. ``"HR 99 ABV2812"`` -> ``"HR99ABV2812"``.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_plate_read(self, read: PlateRead) -> Optional[int]:
        """Insert one plate read; ``None`` if it is a duplicate.

        Duplicate = same (vehicle, camera, normalized plate) already
        stored.  The AI layer's own aggregation logic is untouched.
        """
        normalized = normalize_plate_text(read.normalized_plate or read.raw_ocr)
        if not normalized:
            return None
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO plate_reads (
                    canonical_vehicle_id, camera_id,
                    normalized_plate, raw_ocr,
                    ocr_confidence, detector_confidence,
                    combined_confidence, timestamp, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    read.canonical_vehicle_id,
                    read.camera_id,
                    normalized,
                    read.raw_ocr,
                    read.ocr_confidence,
                    read.detector_confidence,
                    read.combined_confidence,
                    _to_utc_iso(read.timestamp),
                    _to_utc_iso(None),
                ),
            )
        if cur.rowcount == 0:
            return None
        return int(cur.lastrowid)

    def search_exact_plate(self, plate: str) -> List[PlateRead]:
        """Exact match on the normalized plate."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return []
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM plate_reads WHERE normalized_plate = ?"
                " ORDER BY timestamp",
                (normalized,),
            ).fetchall()
        return [_row_to_plate(r) for r in rows]

    def search_partial_plate(self, plate: str) -> List[PlateRead]:
        """Prefix-style match: reads whose normalized plate CONTAINS
        the given fragment (parameterized LIKE, no interpolation)."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return []
        pattern = f"%{normalized}%"
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM plate_reads WHERE normalized_plate LIKE ?"
                " ORDER BY timestamp",
                (pattern,),
            ).fetchall()
        return [_row_to_plate(r) for r in rows]

    def get_plate_reads_for_vehicle(
        self, canonical_vehicle_id: int
    ) -> List[PlateRead]:
        """All plate reads for one canonical vehicle, oldest first."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM plate_reads"
                " WHERE canonical_vehicle_id = ? ORDER BY timestamp",
                (canonical_vehicle_id,),
            ).fetchall()
        return [_row_to_plate(r) for r in rows]

# ---------------------------------------------------------------------------
# Zone count repository
# ---------------------------------------------------------------------------
def _row_to_zone_count(row: sqlite3.Row) -> ZoneCount:
    return ZoneCount(
        id=row["id"],
        camera_id=row["camera_id"],
        canonical_vehicle_id=row["canonical_vehicle_id"],
        vehicle_class=row["vehicle_class"],
        direction=row["direction"],
        timestamp=row["timestamp"],
        created_at=row["created_at"],
    )


class ZoneRepository:
    """Storage and aggregation queries for IN / OUT zone counts.

    Duplicate protection: the Phase 4 ZoneCounter already prevents
    double counting; here, an identical (camera, vehicle, direction,
    class) row inserted twice is silently ignored via INSERT OR IGNORE.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_zone_count(self, count: ZoneCount) -> Optional[int]:
        """Insert one zone count event; ``None`` if duplicate."""
        if count.direction not in ("IN", "OUT"):
            raise ValueError("direction must be 'IN' or 'OUT'")
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO zone_counts (
                    camera_id, canonical_vehicle_id,
                    vehicle_class, direction, timestamp, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    count.camera_id,
                    count.canonical_vehicle_id,
                    count.vehicle_class,
                    count.direction,
                    _to_utc_iso(count.timestamp),
                    _to_utc_iso(None),
                ),
            )
        if cur.rowcount == 0:
            return None
        return int(cur.lastrowid)

    def get_counts(self) -> dict:
        """Aggregate IN/OUT totals per vehicle class, across cameras.

        Returns ``{"total": {"IN": n, "OUT": n}, "<class>": {...}}``.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT vehicle_class, direction, COUNT(*) AS n"
                " FROM zone_counts GROUP BY vehicle_class, direction"
            ).fetchall()
        result: dict = {"total": {"IN": 0, "OUT": 0}}
        for r in rows:
            cls, direction, n = r["vehicle_class"], r["direction"], r["n"]
            bucket = result.setdefault(cls, {"IN": 0, "OUT": 0})
            bucket[direction] += n
            result["total"][direction] += n
        return result

    def get_counts_by_camera(self, camera_id: str) -> dict:
        """Same aggregation as :meth:`get_counts`, for one camera."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT vehicle_class, direction, COUNT(*) AS n"
                " FROM zone_counts WHERE camera_id = ?"
                " GROUP BY vehicle_class, direction",
                (camera_id,),
            ).fetchall()
        result: dict = {"total": {"IN": 0, "OUT": 0}}
        for r in rows:
            cls, direction, n = r["vehicle_class"], r["direction"], r["n"]
            bucket = result.setdefault(cls, {"IN": 0, "OUT": 0})
            bucket[direction] += n
            result["total"][direction] += n
        return result

    def get_counts_by_class(self, vehicle_class: str) -> dict:
        """Aggregate IN/OUT totals for one vehicle class."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT direction, COUNT(*) AS n FROM zone_counts"
                " WHERE vehicle_class = ? GROUP BY direction",
                (vehicle_class,),
            ).fetchall()
        result = {"IN": 0, "OUT": 0}
        for r in rows:
            result[r["direction"]] += r["n"]
        return result
# ---------------------------------------------------------------------------
# Phase 7: Watchlist repository
# ---------------------------------------------------------------------------
class WatchlistRepository:
    """CRUD for watched plates.

    - Reuses ``normalize_plate_text`` (Phase 5) — no duplicate
      normalization exists here.
    - ``"GJ 01 AB 1234"`` and ``"GJ01AB1234"`` map to the same row via
      the UNIQUE ``normalized_plate`` column.
    - Deactivation (``active = 0``) is preferred over deletion.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add_watchlist_entry(self, entry: WatchlistEntry) -> int:
        """Insert one watchlist entry; returns the new row id.

        The plate is normalized here, so callers may pass raw text.
        Raises ``ValueError`` for an empty/unusable plate, an invalid
        category/priority, or a duplicate normalized plate.
        """
        normalized = normalize_plate_text(entry.normalized_plate)
        if not normalized:
            raise ValueError("plate normalizes to an empty value")
        if entry.category not in WATCHLIST_CATEGORIES:
            raise ValueError(
                "category must be one of: " + ", ".join(WATCHLIST_CATEGORIES)
            )
        if entry.priority not in WATCHLIST_PRIORITIES:
            raise ValueError(
                "priority must be one of: " + ", ".join(WATCHLIST_PRIORITIES)
            )
        now = _to_utc_iso(None)
        with self.db.connection() as conn:
            existing = conn.execute(
                "SELECT id FROM watchlist_entries WHERE normalized_plate = ?",
                (normalized,),
            ).fetchone()
            if existing:
                raise ValueError(
                    "watchlist entry already exists for plate " + normalized
                )
            cur = conn.execute(
                """
                INSERT INTO watchlist_entries (
                    normalized_plate, reason, category, priority,
                    notes, active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    entry.reason,
                    entry.category,
                    entry.priority,
                    entry.notes,
                    1 if entry.active else 0,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)



# ---------------------------------------------------------------------------

    def update_watchlist_entry(
        self,
        plate: str,
        reason: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        notes: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> bool:
        """Update selected fields of the entry for *plate* (raw or normalized).

        Only non-``None`` arguments are applied.  Returns True if the
        entry exists and was updated.
        """
        normalized = normalize_plate_text(plate)
        if not normalized:
            raise ValueError("plate normalizes to an empty value")
        if category is not None and category not in WATCHLIST_CATEGORIES:
            raise ValueError(
                "category must be one of: " + ", ".join(WATCHLIST_CATEGORIES)
            )
        if priority is not None and priority not in WATCHLIST_PRIORITIES:
            raise ValueError(
                "priority must be one of: " + ", ".join(WATCHLIST_PRIORITIES)
            )
        assignments, params = [], []
        if reason is not None:
            assignments.append("reason = ?")
            params.append(reason)
        if category is not None:
            assignments.append("category = ?")
            params.append(category)
        if priority is not None:
            assignments.append("priority = ?")
            params.append(priority)
        if notes is not None:
            assignments.append("notes = ?")
            params.append(notes)
        if active is not None:
            assignments.append("active = ?")
            params.append(1 if active else 0)
        if not assignments:
            return False
        assignments.append("updated_at = ?")
        params.append(_to_utc_iso(None))
        params.append(normalized)
        with self.db.connection() as conn:
            cur = conn.execute(
                "UPDATE watchlist_entries SET "
                + ", ".join(assignments)
                + " WHERE normalized_plate = ?",
                params,
            )
        return cur.rowcount > 0


    def get_watchlist_entry(self, entry_id: int) -> Optional[WatchlistEntry]:
        """Return the entry with *entry_id*, or ``None``."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM watchlist_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return _row_to_watchlist_entry(row) if row else None

    def get_watchlist_entry_by_plate(self, plate: str) -> Optional[WatchlistEntry]:
        """Look up an entry by raw or normalized plate text."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return None
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM watchlist_entries WHERE normalized_plate = ?",
                (normalized,),
            ).fetchone()
        return _row_to_watchlist_entry(row) if row else None


    def list_watchlist_entries(
        self,
        active: Optional[bool] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[WatchlistEntry]:
        """List entries with optional active/category/priority filters."""
        clauses, params = [], []
        if active is not None:
            clauses.append("active = ?")
            params.append(1 if active else 0)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        sql = "SELECT * FROM watchlist_entries"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at, id"
        with self.db.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_watchlist_entry(r) for r in rows]

    def deactivate_watchlist_entry(self, plate: str) -> bool:
        """Soft-disable the entry for *plate* (``active = 0``).

        Inactive entries no longer generate alerts.  Returns True if
        the entry exists and was deactivated.
        """
        return self.update_watchlist_entry(plate, active=False)


def _row_to_watchlist_entry(row: sqlite3.Row) -> WatchlistEntry:
    return WatchlistEntry(
        id=int(row["id"]),
        normalized_plate=row["normalized_plate"],
        reason=row["reason"],
        category=row["category"],
        priority=row["priority"],
        notes=row["notes"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Phase 7: Alert repository
# ---------------------------------------------------------------------------
class AlertRepository:
    """Insertion and queries for watchlist alerts."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create_alert(self, alert: Alert) -> int:
        """Insert one alert; returns the new row id."""
        if alert.status not in ALERT_STATUSES:
            raise ValueError(
                "alert status must be one of: " + ", ".join(ALERT_STATUSES)
            )
        if alert.priority not in WATCHLIST_PRIORITIES:
            raise ValueError(
                "priority must be one of: " + ", ".join(WATCHLIST_PRIORITIES)
            )
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO alerts (
                    watchlist_entry_id, normalized_plate,
                    canonical_vehicle_id, camera_id, plate_read_id,
                    vehicle_class, confidence, reason, category,
                    priority, timestamp, status, created_at, acknowledged_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.watchlist_entry_id,
                    alert.normalized_plate,
                    alert.canonical_vehicle_id,
                    alert.camera_id,
                    alert.plate_read_id,
                    alert.vehicle_class,
                    alert.confidence,
                    alert.reason,
                    alert.category,
                    alert.priority,
                    _to_utc_iso(alert.timestamp),
                    alert.status,
                    _to_utc_iso(None),
                    alert.acknowledged_at,
                ),
            )
            return int(cur.lastrowid)

    def get_alert(self, alert_id: int) -> Optional[Alert]:
        """Return the alert with *alert_id*, or ``None``."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
        return _row_to_alert(row) if row else None

    def list_alerts(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        camera_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Alert]:
        """List alerts, newest first, with optional filters."""
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        if camera_id is not None:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        sql = "SELECT * FROM alerts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with self.db.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_alert(r) for r in rows]

    def get_alerts_by_plate(self, plate: str) -> List[Alert]:
        """All alerts for a plate (raw or normalized), newest first."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return []
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE normalized_plate = ?"
                " ORDER BY timestamp DESC, id DESC",
                (normalized,),
            ).fetchall()
        return [_row_to_alert(r) for r in rows]

    def get_alerts_by_camera(self, camera_id: str) -> List[Alert]:
        """All alerts for one camera, newest first."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE camera_id = ?"
                " ORDER BY timestamp DESC, id DESC",
                (camera_id,),
            ).fetchall()
        return [_row_to_alert(r) for r in rows]

    def get_alerts_by_vehicle(self, canonical_vehicle_id: int) -> List[Alert]:
        """All alerts for one canonical vehicle, newest first."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE canonical_vehicle_id = ?"
                " ORDER BY timestamp DESC, id DESC",
                (canonical_vehicle_id,),
            ).fetchall()
        return [_row_to_alert(r) for r in rows]

    def update_alert_status(
        self,
        alert_id: int,
        status: str,
        acknowledged_at: Optional[str] = None,
    ) -> bool:
        """Set the status of an alert.  Returns True if the alert exists.

        When the new status is ACKNOWLEDGED and no acknowledgement time
        is supplied, the current UTC time is recorded.
        """
        if status not in ALERT_STATUSES:
            raise ValueError(
                "alert status must be one of: " + ", ".join(ALERT_STATUSES)
            )
        if acknowledged_at is None and status == "ACKNOWLEDGED":
            acknowledged_at = _to_utc_iso(None)
        with self.db.connection() as conn:
            cur = conn.execute(
                "UPDATE alerts SET status = ?, acknowledged_at = ? WHERE id = ?",
                (status, acknowledged_at, alert_id),
            )
        return cur.rowcount > 0

    def find_recent_new_alert(
        self,
        normalized_plate: str,
        camera_id: str,
        canonical_vehicle_id: int,
    ) -> Optional[Alert]:
        """Most recent NEW alert for (plate, camera, vehicle), if any.

        Used by the AlertEngine for duplicate/cooldown suppression —
        timestamps only, never FPS.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM alerts WHERE normalized_plate = ?"
                " AND camera_id = ? AND canonical_vehicle_id = ?"
                " AND status = 'NEW'"
                " ORDER BY timestamp DESC, id DESC LIMIT 1",
                (normalized_plate, camera_id, canonical_vehicle_id),
            ).fetchone()
        return _row_to_alert(row) if row else None


def _row_to_alert(row: sqlite3.Row) -> Alert:
    return Alert(
        id=int(row["id"]),
        watchlist_entry_id=int(row["watchlist_entry_id"]),
        normalized_plate=row["normalized_plate"],
        canonical_vehicle_id=int(row["canonical_vehicle_id"]),
        camera_id=row["camera_id"],
        plate_read_id=row["plate_read_id"],
        vehicle_class=row["vehicle_class"],
        confidence=row["confidence"],
        reason=row["reason"],
        category=row["category"],
        priority=row["priority"],
        timestamp=row["timestamp"],
        status=row["status"],
        created_at=row["created_at"],
        acknowledged_at=row["acknowledged_at"],
    )


# ---------------------------------------------------------------------------
# Integration bridge — the callable surface for future AI pipeline code
# ---------------------------------------------------------------------------
class EventRecorder:
    """Small integration layer so AI pipeline code can persist results
    without touching SQL (and without being modified).

    Usage
    -----
    ::

        recorder = EventRecorder(db)
        recorder.register_camera(Camera(camera_id="cam01"))
        recorder.record_vehicle_event(...)
        recorder.record_plate_read(...)
        recorder.record_zone_count(...)

    Independent from YOLO / OpenCV.  Foreign keys are enforced, so the
    camera should be registered first (all ``record_*`` methods require
    the camera row to exist).
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.cameras = CameraRepository(db)
        self.vehicles = VehicleRepository(db)
        self.plates = PlateRepository(db)
        self.zones = ZoneRepository(db)
        self.watchlist = WatchlistRepository(db)

    def register_camera(self, camera: Camera) -> int:
        """Upsert a camera (credentials stripped automatically)."""
        return self.cameras.upsert_camera(camera)

    def record_vehicle_event(self, event: VehicleEvent) -> int:
        return self.vehicles.insert_vehicle_event(event)

    def record_plate_read(self, read: PlateRead) -> Optional[int]:
        return self.plates.insert_plate_read(read)

    def record_zone_count(self, count: ZoneCount) -> Optional[int]:
        return self.zones.insert_zone_count(count)


def register_camera(db: Database, camera: Camera) -> int:
    """Module-level convenience: upsert a camera."""
    return CameraRepository(db).upsert_camera(camera)


def record_vehicle_event(db: Database, event: VehicleEvent) -> int:
    """Module-level convenience: persist one vehicle event."""
    return VehicleRepository(db).insert_vehicle_event(event)


def record_plate_read(db: Database, read: PlateRead) -> Optional[int]:
    """Module-level convenience: persist one plate read."""
    return PlateRepository(db).insert_plate_read(read)


def record_zone_count(db: Database, count: ZoneCount) -> Optional[int]:
    """Module-level convenience: persist one zone count."""
    return ZoneRepository(db).insert_zone_count(count)


# ---------------------------------------------------------------------------
# Phase 9.10: Global Vehicle Repository
# ---------------------------------------------------------------------------
def _row_to_global_vehicle(row: sqlite3.Row) -> GlobalVehicle:
    return GlobalVehicle(
        id=int(row["id"]),
        global_vehicle_id=row["global_vehicle_id"],
        normalized_plate=row["normalized_plate"],
        vehicle_class=row["vehicle_class"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_cross_camera_observation(row: sqlite3.Row) -> CrossCameraObservation:
    return CrossCameraObservation(
        id=int(row["id"]),
        global_vehicle_id=row["global_vehicle_id"],
        camera_id=row["camera_id"],
        canonical_vehicle_id=int(row["canonical_vehicle_id"]),
        normalized_plate=row["normalized_plate"],
        vehicle_class=row["vehicle_class"],
        timestamp=row["timestamp"],
        plate_read_id=int(row["plate_read_id"]) if row["plate_read_id"] is not None else None,
        created_at=row["created_at"],
    )


class GlobalVehicleRepository:
    """Manages cross-camera vehicle identities and movement observations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_or_create_by_plate(
        self,
        plate: str,
        vehicle_class: Optional[str] = None,
        timestamp=None,
    ) -> Optional[GlobalVehicle]:
        """Look up an existing GlobalVehicle by plate or create a new one."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return None

        iso_ts = _to_utc_iso(timestamp)
        now = _to_utc_iso(None)

        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM global_vehicles WHERE normalized_plate = ?",
                (normalized,),
            ).fetchone()

            if row:
                gv = _row_to_global_vehicle(row)
                updated_class = vehicle_class or gv.vehicle_class
                conn.execute(
                    """
                    UPDATE global_vehicles
                    SET last_seen_at = ?, vehicle_class = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (iso_ts, updated_class, now, gv.id),
                )
                gv.last_seen_at = iso_ts
                gv.vehicle_class = updated_class
                gv.updated_at = now
                return gv

            # Generate new GV identity
            cur = conn.execute(
                """
                INSERT INTO global_vehicles (
                    global_vehicle_id, normalized_plate, vehicle_class,
                    first_seen_at, last_seen_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("TEMP", normalized, vehicle_class, iso_ts, iso_ts, now, now),
            )
            row_id = cur.lastrowid
            gv_id = f"GV-{row_id:06d}"
            conn.execute(
                "UPDATE global_vehicles SET global_vehicle_id = ? WHERE id = ?",
                (gv_id, row_id),
            )

        return GlobalVehicle(
            id=row_id,
            global_vehicle_id=gv_id,
            normalized_plate=normalized,
            vehicle_class=vehicle_class,
            first_seen_at=iso_ts,
            last_seen_at=iso_ts,
            created_at=now,
            updated_at=now,
        )

    def record_plate_observation(
        self,
        plate: str,
        camera_id: str,
        canonical_vehicle_id: int,
        vehicle_class: Optional[str] = None,
        timestamp=None,
        plate_read_id: Optional[int] = None,
    ) -> Optional[CrossCameraObservation]:
        """Record a confirmed cross-camera appearance of a vehicle."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return None

        gv = self.get_or_create_by_plate(normalized, vehicle_class, timestamp)
        if gv is None:
            return None

        iso_ts = _to_utc_iso(timestamp)
        now = _to_utc_iso(None)

        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO cross_camera_observations (
                    global_vehicle_id, camera_id, canonical_vehicle_id,
                    normalized_plate, vehicle_class, timestamp, plate_read_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gv.global_vehicle_id,
                    camera_id,
                    canonical_vehicle_id,
                    normalized,
                    vehicle_class or gv.vehicle_class,
                    iso_ts,
                    plate_read_id,
                    now,
                ),
            )
            obs_id = cur.lastrowid

        return CrossCameraObservation(
            id=obs_id,
            global_vehicle_id=gv.global_vehicle_id,
            camera_id=camera_id,
            canonical_vehicle_id=canonical_vehicle_id,
            normalized_plate=normalized,
            vehicle_class=vehicle_class or gv.vehicle_class,
            timestamp=iso_ts,
            plate_read_id=plate_read_id,
            created_at=now,
        )

    def get_global_vehicle(self, global_vehicle_id: str) -> Optional[GlobalVehicle]:
        """Return the GlobalVehicle for global_vehicle_id, or None."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM global_vehicles WHERE global_vehicle_id = ?",
                (global_vehicle_id,),
            ).fetchone()
        return _row_to_global_vehicle(row) if row else None

    def get_global_vehicle_by_plate(self, plate: str) -> Optional[GlobalVehicle]:
        """Look up GlobalVehicle by plate (raw or normalized)."""
        normalized = normalize_plate_text(plate)
        if not normalized:
            return None
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM global_vehicles WHERE normalized_plate = ?",
                (normalized,),
            ).fetchone()
        return _row_to_global_vehicle(row) if row else None

    def list_global_vehicles(
        self, limit: int = 100, offset: int = 0
    ) -> List[GlobalVehicle]:
        """List global vehicles ordered by last_seen_at DESC."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM global_vehicles ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()
        return [_row_to_global_vehicle(r) for r in rows]

    def get_timeline(self, global_vehicle_id: str) -> List[CrossCameraObservation]:
        """Return chronological cross-camera observations for a global vehicle."""
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cross_camera_observations
                WHERE global_vehicle_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (global_vehicle_id,),
            ).fetchall()
        return [_row_to_cross_camera_observation(r) for r in rows]

    def get_route(self, global_vehicle_id: str) -> List[dict]:
        """Return chronological GIS route points with resolved camera coordinates."""
        timeline = self.get_timeline(global_vehicle_id)
        if not timeline:
            return []

        cam_repo = CameraRepository(self.db)
        points = []
        for obs in timeline:
            cam = cam_repo.get_camera(obs.camera_id)
            lat = cam.latitude if (cam and cam.latitude is not None) else None
            lon = cam.longitude if (cam and cam.longitude is not None) else None
            points.append(
                {
                    "camera_id": obs.camera_id,
                    "timestamp": obs.timestamp,
                    "latitude": lat,
                    "longitude": lon,
                    "vehicle_class": obs.vehicle_class,
                    "canonical_vehicle_id": obs.canonical_vehicle_id,
                    "normalized_plate": obs.normalized_plate,
                }
            )
        return points


# ---------------------------------------------------------------------------
# Phase 9.12: Camera Health Repository
# ---------------------------------------------------------------------------
def _row_to_camera_health(row: sqlite3.Row) -> CameraHealth:
    return CameraHealth(
        id=int(row["id"]),
        camera_id=row["camera_id"],
        status=row["status"],
        last_successful_frame_at=row["last_successful_frame_at"],
        last_attempt_at=row["last_attempt_at"],
        last_failure_at=row["last_failure_at"],
        consecutive_failures=int(row["consecutive_failures"]),
        reconnect_count=int(row["reconnect_count"]),
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class CameraHealthRepository:
    """Persistence and updates for camera runtime health telemetry."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_health(self, health: CameraHealth) -> int:
        """Insert or update a camera runtime health record."""
        now = _to_utc_iso(None)
        safe_error = redact_url(health.last_error) if health.last_error else health.last_error
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO camera_health (
                    camera_id, status, last_successful_frame_at,
                    last_attempt_at, last_failure_at,
                    consecutive_failures, reconnect_count, last_error,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (camera_id) DO UPDATE SET
                    status                   = excluded.status,
                    last_successful_frame_at = excluded.last_successful_frame_at,
                    last_attempt_at          = excluded.last_attempt_at,
                    last_failure_at          = excluded.last_failure_at,
                    consecutive_failures     = excluded.consecutive_failures,
                    reconnect_count          = excluded.reconnect_count,
                    last_error               = excluded.last_error,
                    updated_at               = excluded.updated_at
                """,
                (
                    health.camera_id,
                    health.status,
                    health.last_successful_frame_at,
                    health.last_attempt_at,
                    health.last_failure_at,
                    health.consecutive_failures,
                    health.reconnect_count,
                    safe_error,
                    health.created_at or now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM camera_health WHERE camera_id = ?",
                (health.camera_id,),
            ).fetchone()
            return int(row["id"])

    def record_success(self, camera_id: str, timestamp: Optional[str] = None) -> CameraHealth:
        """Record a successful frame read observation for a camera."""
        now = _to_utc_iso(timestamp)
        existing = self.get_health(camera_id)
        reconnects = existing.reconnect_count if existing else 0
        status = "DEGRADED" if reconnects > 0 else "ONLINE"
        health = CameraHealth(
            camera_id=camera_id,
            status=status,
            last_successful_frame_at=now,
            last_attempt_at=now,
            last_failure_at=existing.last_failure_at if existing else None,
            consecutive_failures=0,
            reconnect_count=reconnects,
            last_error=existing.last_error if existing else None,
        )
        self.upsert_health(health)
        return self.get_health(camera_id)  # type: ignore

    def record_failure(
        self,
        camera_id: str,
        error_msg: Optional[str] = None,
        timestamp: Optional[str] = None,
        consecutive: Optional[int] = None,
    ) -> CameraHealth:
        """Record a stream connection/read failure observation for a camera."""
        now = _to_utc_iso(timestamp)
        existing = self.get_health(camera_id)
        prev_consec = existing.consecutive_failures if existing else 0
        new_consec = consecutive if consecutive is not None else (prev_consec + 1)
        reconnects = existing.reconnect_count if existing else 0
        last_success = existing.last_successful_frame_at if existing else None

        if new_consec >= 60 or (existing and existing.status == "OFFLINE"):
            status = "OFFLINE"
        elif new_consec >= 1 or reconnects > 0:
            status = "DEGRADED"
        else:
            status = "OFFLINE"

        safe_err = redact_url(error_msg) if error_msg else (existing.last_error if existing else "Read/connect failure")

        health = CameraHealth(
            camera_id=camera_id,
            status=status,
            last_successful_frame_at=last_success,
            last_attempt_at=now,
            last_failure_at=now,
            consecutive_failures=new_consec,
            reconnect_count=reconnects,
            last_error=safe_err,
        )
        self.upsert_health(health)
        return self.get_health(camera_id)  # type: ignore

    def record_reconnect(self, camera_id: str, timestamp: Optional[str] = None) -> CameraHealth:
        """Record a stream reconnect attempt."""
        now = _to_utc_iso(timestamp)
        existing = self.get_health(camera_id)
        reconnects = (existing.reconnect_count + 1) if existing else 1
        last_success = existing.last_successful_frame_at if existing else None
        last_err = existing.last_error if existing else "Stream reconnecting"

        health = CameraHealth(
            camera_id=camera_id,
            status="DEGRADED",
            last_successful_frame_at=last_success,
            last_attempt_at=now,
            last_failure_at=now,
            consecutive_failures=0,
            reconnect_count=reconnects,
            last_error=last_err,
        )
        self.upsert_health(health)
        return self.get_health(camera_id)  # type: ignore

    def get_health(self, camera_id: str) -> Optional[CameraHealth]:
        """Return the runtime health record for camera_id, or None."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM camera_health WHERE camera_id = ?",
                (camera_id,),
            ).fetchone()
        return _row_to_camera_health(row) if row else None

    def list_health(self) -> List[CameraHealth]:
        """Return all runtime health records ordered by camera_id."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM camera_health ORDER BY camera_id"
            ).fetchall()
        return [_row_to_camera_health(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 9.14: Audit Logging Repository
# ---------------------------------------------------------------------------
def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        actor=row["actor"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        result=row["result"],
        metadata_json=row["metadata_json"],
        timestamp=row["timestamp"],
    )


class AuditRepository:
    """Repository for managing security and administration audit logs."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add_audit_entry(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        result: str = "SUCCESS",
        metadata_json: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> AuditLog:
        """Create and persist a new audit log entry."""
        iso_ts = _to_utc_iso(timestamp)
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_logs (
                    actor, action, resource_type, resource_id, result, metadata_json, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor,
                    action,
                    resource_type,
                    resource_id,
                    result,
                    metadata_json,
                    iso_ts,
                ),
            )
            audit_id = cur.lastrowid

        return AuditLog(
            id=audit_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            metadata_json=metadata_json,
            timestamp=iso_ts,
        )

    def list_audit_entries(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLog]:
        """List audit log entries ordered by timestamp DESC."""
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        if actor:
            query += " AND actor = ?"
            params.append(actor)
        if action:
            query += " AND action = ?"
            params.append(action)

        query += " ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_audit_log(r) for r in rows]








