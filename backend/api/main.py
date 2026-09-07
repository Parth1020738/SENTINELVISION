"""
SentinelVision - FastAPI application

Phase 6C: REST API on top of the existing SQLite repositories.

Security
--------
- Camera responses expose safe metadata ONLY (no rtsp_url / webrtc_url
  / hls_url), so authenticated RTSP credentials can never leak.
- Errors return generic messages — no SQL, filesystem paths, stack
  traces, or credentials.
- CORS origins are configurable via the ``SENTINELVISION_CORS_ORIGINS``
  environment variable (comma-separated) for the local dashboard.
"""

import os
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.deps import Repositories, get_repositories
from backend.camera.camera_catalogue import NormalizedCamera, global_catalogue
from backend.services.attention_engine import AttentionEngine
from backend.services.event_hub import event_hub
from backend.api.schemas import (
    AlertListResponse,
    AlertResponse,
    AlertStatusUpdate,
    CameraPlaybackResponse,
    CameraResponse,
    CountsResponse,
    DirectionTotals,
    PlateReadResponse,
    PlateSearchResponse,
    VehicleEventResponse,
    WatchlistEntryCreate,
    WatchlistEntryResponse,
    WatchlistEntryUpdate,
    WatchlistListResponse,
)
from backend.ai.plate_ocr import normalize_plate_text
from backend.db.models import (
    ALERT_STATUSES,
    WATCHLIST_CATEGORIES,
    WATCHLIST_PRIORITIES,
    Alert,
    Camera,
    PlateRead,
    VehicleEvent,
    WatchlistEntry,
)

app = FastAPI(
    title="SentinelVision API",
    version="1.0.0",
    description="REST API over the SentinelVision SQLite persistence layer.",
)

# ---------------------------------------------------------------------------
# CORS — configurable for the future local dashboard
# ---------------------------------------------------------------------------
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://127.0.0.1:8000"
)


def _cors_origins() -> List[str]:
    raw = os.environ.get("SENTINELVISION_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handling — never leak internals to clients
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Logged detail stays server-side; clients get a generic 500.
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )



# ---------------------------------------------------------------------------
# Conversion helpers (dataclass -> API schema)
# ---------------------------------------------------------------------------
def _watchlist_to_response(entry: WatchlistEntry) -> WatchlistEntryResponse:
    return WatchlistEntryResponse(
        id=int(entry.id),
        normalized_plate=entry.normalized_plate,
        reason=entry.reason,
        category=entry.category,
        priority=entry.priority,
        notes=entry.notes,
        active=entry.active,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _alert_to_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=int(alert.id),
        watchlist_entry_id=alert.watchlist_entry_id,
        normalized_plate=alert.normalized_plate,
        canonical_vehicle_id=alert.canonical_vehicle_id,
        camera_id=alert.camera_id,
        plate_read_id=alert.plate_read_id,
        vehicle_class=alert.vehicle_class,
        confidence=alert.confidence,
        reason=alert.reason,
        category=alert.category,
        priority=alert.priority,
        timestamp=alert.timestamp,
        status=alert.status,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
    )


def _compute_attention_state(camera, repos: Repositories):
    try:
        res = AttentionEngine.evaluate(camera, repos=repos)
        return res.attention_state, res.attention_reason
    except Exception:
        return "NORMAL", None


def _camera_to_response(
    camera, attention_state: str = "NORMAL", attention_reason: Optional[str] = None
) -> CameraResponse:
    if isinstance(camera, NormalizedCamera):
        return CameraResponse(
            camera_id=camera.camera_id,
            name=camera.name,
            location=camera.location,
            latitude=camera.latitude,
            longitude=camera.longitude,
            codec=camera.codec,
            width=camera.width,
            height=camera.height,
            resolution=camera.resolution,
            live=camera.live,
            status=camera.status,
            ai_active=camera.ai_active,
            attention_state=attention_state,
            attention_reason=attention_reason,
        )

    res = getattr(camera, "resolution", None)
    if not res and getattr(camera, "width", None) and getattr(camera, "height", None):
        res = f"{camera.width}x{camera.height}"

    cam_id = str(getattr(camera, "camera_id", ""))
    return CameraResponse(
        camera_id=cam_id,
        name=getattr(camera, "name", None),
        location=getattr(camera, "location", None),
        latitude=getattr(camera, "latitude", None),
        longitude=getattr(camera, "longitude", None),
        codec=getattr(camera, "codec", None),
        width=getattr(camera, "width", None),
        height=getattr(camera, "height", None),
        resolution=res,
        live=bool(getattr(camera, "live", False)),
        status="online" if getattr(camera, "live", False) else "offline",
        ai_active=(cam_id == "cam01"),
        attention_state=attention_state,
        attention_reason=attention_reason,
        created_at=getattr(camera, "created_at", None),
        updated_at=getattr(camera, "updated_at", None),
    )


def _event_to_response(event: VehicleEvent) -> VehicleEventResponse:
    return VehicleEventResponse(
        id=event.id,
        canonical_vehicle_id=event.canonical_vehicle_id,
        camera_id=event.camera_id,
        vehicle_class=event.vehicle_class,
        event_type=event.event_type,
        timestamp=event.timestamp,
        confidence=event.confidence,
        bbox_x1=event.bbox_x1,
        bbox_y1=event.bbox_y1,
        bbox_x2=event.bbox_x2,
        bbox_y2=event.bbox_y2,
        direction=event.direction,
        created_at=event.created_at,
    )


def _plate_to_response(read: PlateRead) -> PlateReadResponse:
    return PlateReadResponse(
        id=read.id,
        canonical_vehicle_id=read.canonical_vehicle_id,
        camera_id=read.camera_id,
        normalized_plate=read.normalized_plate,
        raw_ocr=read.raw_ocr,
        ocr_confidence=read.ocr_confidence,
        detector_confidence=read.detector_confidence,
        combined_confidence=read.combined_confidence,
        timestamp=read.timestamp,
        created_at=read.created_at,
    )



# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health(repos: Repositories = Depends(get_repositories)):
    """Liveness probe.  Also reports database availability.

    Never touches RTSP / cameras — database only.
    """
    database_ok = True
    try:
        repos.db.table_names()
    except Exception:
        database_ok = False
    return {"status": "ok", "database": "ok" if database_ok else "unavailable"}


# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------
@app.get("/api/cameras", response_model=List[CameraResponse])
def list_cameras(repos: Repositories = Depends(get_repositories)):
    """All registered cameras (safe metadata only)."""
    catalogue_cams = global_catalogue.get_cameras()
    db_cams = repos.cameras.list_cameras()

    cam_map = {}
    for c in catalogue_cams:
        cam_map[c.camera_id] = c

    for db_c in db_cams:
        if db_c.camera_id in cam_map:
            cat_c = cam_map[db_c.camera_id]
            if db_c.name and db_c.name != f"Camera {db_c.camera_id}":
                cat_c.name = db_c.name
            if db_c.location:
                cat_c.location = db_c.location
            if db_c.latitude is not None:
                cat_c.latitude = db_c.latitude
            if db_c.longitude is not None:
                cat_c.longitude = db_c.longitude
            if db_c.width:
                cat_c.width = db_c.width
            if db_c.height:
                cat_c.height = db_c.height
                cat_c.resolution = f"{db_c.width}x{db_c.height}"
        else:
            cam_map[db_c.camera_id] = db_c

    responses = []
    for cam_id, cam in cam_map.items():
        att_state, att_reason = _compute_attention_state(cam, repos)
        responses.append(
            _camera_to_response(
                cam, attention_state=att_state, attention_reason=att_reason
            )
        )

    return responses


@app.get("/api/cameras/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: str, repos: Repositories = Depends(get_repositories)
):
    """One camera by id; 404 if unknown."""
    cameras = list_cameras(repos=repos)
    for c in cameras:
        if c.camera_id == camera_id:
            return c

    raise HTTPException(
        status_code=404, detail=f"Camera '{camera_id}' not found"
    )


@app.get("/api/cameras/{camera_id}/playback", response_model=CameraPlaybackResponse)
def get_camera_playback(
    camera_id: str, repos: Repositories = Depends(get_repositories)
):
    """Return browser-safe camera playback metadata.

    The returned payload MUST contain safe playback URLs only (e.g. HLS).
    It NEVER exposes RTSP credentials, usernames, passwords, or
    authenticated RTSP/WebRTC URLs.
    """
    cameras = list_cameras(repos=repos)
    cam = next((c for c in cameras if c.camera_id == camera_id), None)

    if cam is None:
        raise HTTPException(
            status_code=404, detail=f"Camera '{camera_id}' not found"
        )

    # Official HLS browser stream contract
    playback_url = f"https://cctv.corp8.cloud/{camera_id}/index.m3u8"

    return CameraPlaybackResponse(
        camera_id=camera_id,
        playback_type="hls",
        playback_url=playback_url,
        available=True,
    )



# ---------------------------------------------------------------------------
# Vehicle history
# ---------------------------------------------------------------------------
@app.get(
    "/api/vehicles/{canonical_vehicle_id}/history",
    response_model=List[VehicleEventResponse],
)
def vehicle_history(
    canonical_vehicle_id: int,
    repos: Repositories = Depends(get_repositories),
):
    """All events for one canonical vehicle, oldest first."""
    events = repos.vehicles.get_vehicle_history(canonical_vehicle_id)
    return [_event_to_response(e) for e in events]



# ---------------------------------------------------------------------------
# Plate search
# ---------------------------------------------------------------------------
@app.get("/api/plates/search", response_model=PlateSearchResponse)
def search_plates(
    plate: str = Query(..., min_length=1, description="Plate text to search"),
    match: str = Query(
        "exact", pattern="^(exact|partial)$", description="Match mode"
    ),
    repos: Repositories = Depends(get_repositories),
):
    """Exact or partial plate search.

    Input is normalized with the existing Phase 5 logic
    (``backend.ai.plate_ocr.normalize_plate_text``), e.g.
    ``"HR 99 ABV2812"`` -> ``"HR99ABV2812"``.
    """
    normalized = normalize_plate_text(plate)
    if not normalized:
        raise HTTPException(
            status_code=400, detail="Plate text normalizes to an empty value"
        )
    if match == "exact":
        reads = repos.plates.search_exact_plate(plate)
    else:
        reads = repos.plates.search_partial_plate(plate)
    return PlateSearchResponse(
        query=plate,
        normalized_query=normalized,
        match=match,
        count=len(reads),
        results=[_plate_to_response(r) for r in reads],
    )


# ---------------------------------------------------------------------------
# Zone counts
# ---------------------------------------------------------------------------
@app.get("/api/counts", response_model=CountsResponse)
def get_counts(
    camera_id: Optional[str] = Query(None),
    vehicle_class: Optional[str] = Query(None),
    direction: Optional[str] = Query(
        None, pattern="^(IN|OUT)$", description="Filter by direction"
    ),
    repos: Repositories = Depends(get_repositories),
):
    """Aggregated IN/OUT zone counts with optional filters."""
    filters = {
        "camera_id": camera_id,
        "vehicle_class": vehicle_class,
        "direction": direction,
    }

    if camera_id:
        aggregate = repos.zones.get_counts_by_camera(camera_id)
    elif vehicle_class:
        totals = repos.zones.get_counts_by_class(vehicle_class)
        aggregate = {"total": totals, vehicle_class: dict(totals)}
    else:
        aggregate = repos.zones.get_counts()

    total = DirectionTotals(**aggregate.get("total", {"IN": 0, "OUT": 0}))
    by_class = {
        key: value
        for key, value in aggregate.items()
        if key != "total" and isinstance(value, dict)
    }

    if direction:
        total = DirectionTotals(
            IN=total.IN if direction == "IN" else 0,
            OUT=total.OUT if direction == "OUT" else 0,
        )
        by_class = {
            cls: {
                "IN": counts.get("IN", 0) if direction == "IN" else 0,
                "OUT": counts.get("OUT", 0) if direction == "OUT" else 0,
            }
            for cls, counts in by_class.items()
        }

    return CountsResponse(filters=filters, total=total, by_class=by_class)


# ---------------------------------------------------------------------------
# Phase 7: Watchlist endpoints
# ---------------------------------------------------------------------------
def _require_category(category: str) -> None:
    if category not in WATCHLIST_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="category must be one of: " + ", ".join(WATCHLIST_CATEGORIES),
        )


def _require_priority(priority: str) -> None:
    if priority not in WATCHLIST_PRIORITIES:
        raise HTTPException(
            status_code=400,
            detail="priority must be one of: " + ", ".join(WATCHLIST_PRIORITIES),
        )


@app.get("/api/watchlist", response_model=WatchlistListResponse)
def list_watchlist(
    active: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    repos: Repositories = Depends(get_repositories),
):
    """List watchlist entries with optional filters."""
    if category is not None:
        _require_category(category)
    if priority is not None:
        _require_priority(priority)
    entries = repos.watchlist.list_watchlist_entries(
        active=active, category=category, priority=priority
    )
    return WatchlistListResponse(
        count=len(entries),
        results=[_watchlist_to_response(e) for e in entries],
    )


@app.get("/api/watchlist/{plate}", response_model=WatchlistEntryResponse)
def get_watchlist_entry(
    plate: str,
    repos: Repositories = Depends(get_repositories),
):
    """One watchlist entry by plate (raw or normalized text)."""
    entry = repos.watchlist.get_watchlist_entry_by_plate(plate)
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return _watchlist_to_response(entry)


@app.post("/api/watchlist", response_model=WatchlistEntryResponse, status_code=201)
def create_watchlist_entry(
    payload: WatchlistEntryCreate,
    repos: Repositories = Depends(get_repositories),
):
    """Add a watched plate.  The plate is normalized before storage.

    Duplicate normalized plates return 409 Conflict.
    """
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="reason is required")
    _require_category(payload.category)
    _require_priority(payload.priority)

    entry = WatchlistEntry(
        normalized_plate=payload.plate,
        reason=payload.reason.strip(),
        category=payload.category,
        priority=payload.priority,
        notes=payload.notes,
        active=True,
    )
    try:
        entry_id = repos.watchlist.add_watchlist_entry(entry)
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=400, detail=message)
    created = repos.watchlist.get_watchlist_entry(entry_id)
    return _watchlist_to_response(created)


@app.patch("/api/watchlist/{plate}", response_model=WatchlistEntryResponse)
def patch_watchlist_entry(
    plate: str,
    payload: WatchlistEntryUpdate,
    repos: Repositories = Depends(get_repositories),
):
    """Update selected fields of a watchlist entry."""
    if payload.category is not None:
        _require_category(payload.category)
    if payload.priority is not None:
        _require_priority(payload.priority)
    try:
        updated = repos.watchlist.update_watchlist_entry(
            plate,
            reason=payload.reason,
            category=payload.category,
            priority=payload.priority,
            notes=payload.notes,
            active=payload.active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    entry = repos.watchlist.get_watchlist_entry_by_plate(plate)
    return _watchlist_to_response(entry)


@app.delete("/api/watchlist/{plate}")
def delete_watchlist_entry(
    plate: str,
    repos: Repositories = Depends(get_repositories),
):
    """Soft-disable a watchlist entry (active=False, no data loss)."""
    try:
        ok = repos.watchlist.deactivate_watchlist_entry(plate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return {
        "detail": "Watchlist entry deactivated",
        "plate": normalize_plate_text(plate),
    }


# ---------------------------------------------------------------------------
# Phase 7: Alert endpoints
# ---------------------------------------------------------------------------
@app.get("/api/alerts", response_model=AlertListResponse)
def list_alerts(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    plate: Optional[str] = Query(None),
    repos: Repositories = Depends(get_repositories),
):
    """List alerts, newest first, with optional filters."""
    if status is not None and status not in ALERT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: " + ", ".join(ALERT_STATUSES),
        )
    if priority is not None:
        _require_priority(priority)

    if plate is not None:
        alerts = repos.alerts.get_alerts_by_plate(plate)
        alerts = [
            a
            for a in alerts
            if (status is None or a.status == status)
            and (priority is None or a.priority == priority)
            and (camera_id is None or a.camera_id == camera_id)
        ]
    else:
        alerts = repos.alerts.list_alerts(
            status=status, priority=priority, camera_id=camera_id
        )
    return AlertListResponse(
        count=len(alerts), results=[_alert_to_response(a) for a in alerts]
    )


@app.get("/api/alerts/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: int,
    repos: Repositories = Depends(get_repositories),
):
    """One alert by id."""
    alert = repos.alerts.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _alert_to_response(alert)


@app.patch("/api/alerts/{alert_id}/status", response_model=AlertResponse)
def update_alert_status(
    alert_id: int,
    payload: AlertStatusUpdate,
    repos: Repositories = Depends(get_repositories),
):
    """Update the status of an alert (NEW / ACKNOWLEDGED / RESOLVED)."""
    if payload.status not in ALERT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: " + ", ".join(ALERT_STATUSES),
        )
    try:
        ok = repos.alerts.update_alert_status(alert_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert = repos.alerts.get_alert(alert_id)
    if alert is not None:
        try:
            event_hub.publish_sync(
                "alert_status_changed",
                camera_id=alert.camera_id,
                data={
                    "alert_id": alert.id,
                    "status": alert.status,
                    "normalized_plate": alert.normalized_plate,
                },
            )
            att_state, att_reason = _compute_attention_state(alert.camera_id, repos)
            event_hub.publish_sync(
                "attention_changed",
                camera_id=alert.camera_id,
                data={
                    "attention_state": att_state,
                    "attention_reason": att_reason,
                },
            )
        except Exception:
            pass
    return _alert_to_response(alert)


# ---------------------------------------------------------------------------
# Phase 9.6: Real-time WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/api/events/ws")
async def websocket_events_endpoint(websocket: WebSocket):
    """Real-time WebSocket event stream for dashboard clients."""
    await websocket.accept()
    event_hub.register(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        event_hub.unregister(websocket)
    except Exception:
        event_hub.unregister(websocket)


def run():  # pragma: no cover - manual convenience entry point
    import uvicorn

    uvicorn.run(
        "backend.api.main:app", host="127.0.0.1", port=8000, reload=False
    )
