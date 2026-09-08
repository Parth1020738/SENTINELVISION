"""
SentinelVision - Database Models

Phase 6B: SQLite Persistence Layer

Lightweight dataclasses representing database records.  These models
have NO dependency on YOLO / OpenCV / camera code — they are plain
data carriers for the persistence layer.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Camera record
# ---------------------------------------------------------------------------
@dataclass
class Camera:
    """One camera in the SentinelVision catalogue.

    ``camera_id`` is the stable identity (e.g. ``cam01``).  The RTSP
    URL stored here must NEVER contain credentials — the persistence
    layer strips userinfo defensively before writing.
    """

    camera_id: str
    name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    rtsp_url: Optional[str] = None
    webrtc_url: Optional[str] = None
    hls_url: Optional[str] = None
    live: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Vehicle event record
# ---------------------------------------------------------------------------
@dataclass
class VehicleEvent:
    """One meaningful vehicle event (NOT one row per video frame).

    ``event_type`` examples: DETECTED, ZONE_IN, ZONE_OUT, TRACK_END.
    ``timestamp`` is supplied by the caller (source PTS when available);
    the database layer never derives timing from FPS.
    """

    canonical_vehicle_id: int
    camera_id: str
    vehicle_class: str
    event_type: str
    timestamp: Optional[str] = None
    confidence: Optional[float] = None
    bbox_x1: Optional[float] = None
    bbox_y1: Optional[float] = None
    bbox_x2: Optional[float] = None
    bbox_y2: Optional[float] = None
    direction: Optional[str] = None
    created_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Plate read record
# ---------------------------------------------------------------------------
@dataclass
class PlateRead:
    """One aggregated plate read for a canonical vehicle.

    ``normalized_plate`` must already be normalized via
    ``backend.ai.plate_ocr.normalize_plate_text`` — the database layer
    does not implement a competing normalization.
    """

    canonical_vehicle_id: int
    camera_id: str
    raw_ocr: str
    timestamp: Optional[str] = None
    normalized_plate: Optional[str] = None
    ocr_confidence: Optional[float] = None
    detector_confidence: Optional[float] = None
    combined_confidence: Optional[float] = None
    created_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Zone count record
# ---------------------------------------------------------------------------
@dataclass
class ZoneCount:
    """One IN / OUT zone counting event."""

    camera_id: str
    canonical_vehicle_id: int
    vehicle_class: str
    direction: str  # "IN" or "OUT"
    timestamp: Optional[str] = None
    created_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Phase 7: Watchlist + alerts
# ---------------------------------------------------------------------------
# Shared vocabularies — validated but deliberately simple.
WATCHLIST_CATEGORIES = ("STOLEN", "WANTED", "SUSPICIOUS", "INVESTIGATION", "OTHER")
WATCHLIST_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
ALERT_STATUSES = ("NEW", "ACKNOWLEDGED", "RESOLVED")


@dataclass
class WatchlistEntry:
    """One watched (suspicious/wanted/stolen) plate.

    ``normalized_plate`` must already be normalized via
    ``backend.ai.plate_ocr.normalize_plate_text`` — the storage layer
    reuses the Phase 5 normalization and never implements its own.
    """

    normalized_plate: str
    reason: str
    category: str = "OTHER"
    priority: str = "MEDIUM"
    notes: Optional[str] = None
    active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)


@dataclass
class Alert:
    """One alert raised because a watched plate was observed by ANPR."""

    watchlist_entry_id: int
    normalized_plate: str
    canonical_vehicle_id: int
    camera_id: str
    plate_read_id: Optional[int] = None
    vehicle_class: Optional[str] = None
    confidence: Optional[float] = None
    reason: str = ""
    category: str = "OTHER"
    priority: str = "MEDIUM"
    timestamp: Optional[str] = None
    status: str = "NEW"
    created_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Phase 9.10: Cross-Camera Vehicle Tracking
# ---------------------------------------------------------------------------
@dataclass
class GlobalVehicle:
    """A cross-camera global vehicle identity, indexed by normalized plate."""

    global_vehicle_id: str
    normalized_plate: Optional[str] = None
    vehicle_class: Optional[str] = None
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)


@dataclass
class CrossCameraObservation:
    """A confirmed appearance of a global vehicle on a specific camera stream."""

    global_vehicle_id: str
    camera_id: str
    canonical_vehicle_id: int
    normalized_plate: Optional[str] = None
    vehicle_class: Optional[str] = None
    timestamp: Optional[str] = None
    plate_read_id: Optional[int] = None
    created_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)
