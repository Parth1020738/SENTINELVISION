"""
SentinelVision - Pydantic API schemas

Phase 6C: API response models.  These are deliberately separate from
the dataclass models in ``backend.db.models`` and have NO dependency on
YOLO / OpenCV / camera code.

Security: camera responses expose safe metadata only — no rtsp_url /
webrtc_url / hls_url, so credentials can never leak through the API.
"""

from typing import List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
class CameraResponse(BaseModel):
    """Safe camera metadata (no stream URLs, no credentials)."""

    camera_id: str
    name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    resolution: Optional[str] = None
    live: bool = False
    status: str = "available"
    ai_active: bool = False
    attention_state: str = "NORMAL"
    attention_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CameraPlaybackResponse(BaseModel):
    """Safe browser playback metadata (no credentials, no authenticated RTSP)."""

    camera_id: str
    playback_type: str = "hls"
    playback_url: str
    available: bool = True


# ---------------------------------------------------------------------------
# Vehicle events
# ---------------------------------------------------------------------------
class VehicleEventResponse(BaseModel):
    id: Optional[int] = None
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


# ---------------------------------------------------------------------------
# Plate reads
# ---------------------------------------------------------------------------
class PlateReadResponse(BaseModel):
    id: Optional[int] = None
    canonical_vehicle_id: int
    camera_id: str
    normalized_plate: Optional[str] = None
    raw_ocr: Optional[str] = None
    ocr_confidence: Optional[float] = None
    detector_confidence: Optional[float] = None
    combined_confidence: Optional[float] = None
    timestamp: Optional[str] = None
    created_at: Optional[str] = None


class PlateSearchResponse(BaseModel):
    """Response for GET /api/plates/search."""

    query: str
    normalized_query: str
    match: str  # "exact" or "partial"
    count: int
    results: List[PlateReadResponse]


# ---------------------------------------------------------------------------
# Zone counts
# ---------------------------------------------------------------------------
class DirectionTotals(BaseModel):
    IN: int = 0
    OUT: int = 0


class CountsResponse(BaseModel):
    """Aggregated IN/OUT zone counts with the filters that were applied."""

    filters: dict
    total: DirectionTotals
    by_class: dict  # {vehicle_class: {"IN": n, "OUT": n}}


# ---------------------------------------------------------------------------
# Phase 7: Watchlist
# ---------------------------------------------------------------------------
class WatchlistEntryCreate(BaseModel):
    """POST /api/watchlist body."""

    plate: str
    reason: str
    category: str = "OTHER"
    priority: str = "MEDIUM"
    notes: Optional[str] = None


class WatchlistEntryUpdate(BaseModel):
    """PATCH /api/watchlist/{plate} body — only supplied fields change."""

    reason: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class WatchlistEntryResponse(BaseModel):
    id: int
    normalized_plate: str
    reason: str
    category: str
    priority: str
    notes: Optional[str] = None
    active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WatchlistListResponse(BaseModel):
    count: int
    results: List[WatchlistEntryResponse]


# ---------------------------------------------------------------------------
# Phase 7: Alerts
# ---------------------------------------------------------------------------
class AlertResponse(BaseModel):
    id: int
    watchlist_entry_id: int
    normalized_plate: str
    canonical_vehicle_id: int
    camera_id: str
    plate_read_id: Optional[int] = None
    vehicle_class: Optional[str] = None
    confidence: Optional[float] = None
    reason: str
    category: str
    priority: str
    timestamp: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    acknowledged_at: Optional[str] = None


class AlertListResponse(BaseModel):
    count: int
    results: List[AlertResponse]


class AlertStatusUpdate(BaseModel):
    """PATCH /api/alerts/{alert_id}/status body."""

    status: str
