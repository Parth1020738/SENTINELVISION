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

from backend.api.deps import Repositories, get_repositories, get_current_user, require_role
from backend.auth import authenticate_user, create_access_token, check_rate_limit, record_failed_login, verify_access_code
from backend.camera.camera_catalogue import NormalizedCamera, global_catalogue
from backend.services.attention_engine import AttentionEngine
from backend.services.event_hub import event_hub
from backend.api.schemas import (
    AccessCodeVerifyRequest,
    AlertListResponse,
    AlertResponse,
    AlertStatusUpdate,
    AuditLogListResponse,
    AuditLogResponse,
    CameraHealthResponse,
    CameraPlaybackResponse,
    CameraResponse,
    CountsResponse,
    CrossCameraObservationResponse,
    DirectionTotals,
    GlobalVehicleListResponse,
    GlobalVehicleResponse,
    GlobalVehicleRouteResponse,
    GlobalVehicleTimelineResponse,
    HealthSummaryCounts,
    LoginRequest,
    PlateReadResponse,
    PlateSearchResponse,
    RoutePointResponse,
    SystemHealthResponse,
    TokenResponse,
    UserResponse,
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
    AuditLog,
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
    raw = os.environ.get("SENTINEL_FRONTEND_ORIGIN") or os.environ.get("SENTINELVISION_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Lightweight middleware injecting standard HTTP security headers."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


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
# Phase 9.14: Authentication & Audit Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    repos: Repositories = Depends(get_repositories),
):
    """Authenticate administrator or operator credentials and return a bearer token."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip, max_attempts=5, window_seconds=60):
        repos.audit.add_audit_entry(
            actor=payload.username or "unknown",
            action="LOGIN_RATE_LIMITED",
            resource_type="auth",
            result="FAILURE",
            metadata_json=f'{{"ip": "{client_ip}"}}',
        )
        raise HTTPException(
            status_code=429, detail="Too many failed login attempts. Please wait 1 minute."
        )

    user = authenticate_user(payload.username, payload.password)
    if not user:
        record_failed_login(client_ip)
        repos.audit.add_audit_entry(
            actor=payload.username or "unknown",
            action="LOGIN_FAILED",
            resource_type="auth",
            result="FAILURE",
            metadata_json=f'{{"ip": "{client_ip}"}}',
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user["username"], user["role"])
    repos.audit.add_audit_entry(
        actor=user["username"],
        action="LOGIN_SUCCESS",
        resource_type="auth",
        result="SUCCESS",
        metadata_json=f'{{"role": "{user["role"]}", "ip": "{client_ip}"}}',
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
    )


@app.post("/api/auth/verify-access-code", response_model=TokenResponse)
def verify_access_code_endpoint(
    payload: AccessCodeVerifyRequest,
    request: Request,
    repos: Repositories = Depends(get_repositories),
):
    """Verify system access code and return a bearer session token."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip, max_attempts=5, window_seconds=60):
        repos.audit.add_audit_entry(
            actor="access_gate",
            action="ACCESS_CODE_RATE_LIMITED",
            resource_type="auth",
            result="FAILURE",
            metadata_json=f'{{"ip": "{client_ip}"}}',
        )
        raise HTTPException(
            status_code=429, detail="Too many failed access code attempts. Please wait 1 minute."
        )

    if not verify_access_code(payload.access_code):
        record_failed_login(client_ip)
        repos.audit.add_audit_entry(
            actor="access_gate",
            action="ACCESS_CODE_FAILED",
            resource_type="auth",
            result="FAILURE",
            metadata_json=f'{{"ip": "{client_ip}"}}',
        )
        raise HTTPException(status_code=401, detail="Invalid access code")

    token = create_access_token("access_user", "ADMIN")
    repos.audit.add_audit_entry(
        actor="access_user",
        action="ACCESS_CODE_SUCCESS",
        resource_type="auth",
        result="SUCCESS",
        metadata_json=f'{{"ip": "{client_ip}"}}',
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role="ADMIN",
        username="access_user",
    )


@app.get("/api/auth/me", response_model=UserResponse)
def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Return profile info for the authenticated token."""
    return UserResponse(username=user["username"], role=user["role"])


@app.get("/api/audit", response_model=AuditLogListResponse)
def list_audit_logs(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_role("ADMIN")),
    repos: Repositories = Depends(get_repositories),
):
    """Retrieve security audit logs (ADMIN role required)."""
    logs = repos.audit.list_audit_entries(actor=actor, action=action, limit=limit, offset=offset)
    return AuditLogListResponse(
        count=len(logs),
        results=[
            AuditLogResponse(
                id=l.id,
                actor=l.actor,
                action=l.action,
                resource_type=l.resource_type,
                resource_id=l.resource_id,
                result=l.result,
                metadata_json=l.metadata_json,
                timestamp=l.timestamp,
            )
            for l in logs
        ],
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


def _global_vehicle_to_response(gv) -> GlobalVehicleResponse:
    return GlobalVehicleResponse(
        id=int(gv.id),
        global_vehicle_id=gv.global_vehicle_id,
        normalized_plate=gv.normalized_plate,
        vehicle_class=gv.vehicle_class,
        first_seen_at=gv.first_seen_at,
        last_seen_at=gv.last_seen_at,
        created_at=gv.created_at,
        updated_at=gv.updated_at,
    )


def _observation_to_response(obs) -> CrossCameraObservationResponse:
    return CrossCameraObservationResponse(
        id=int(obs.id),
        global_vehicle_id=obs.global_vehicle_id,
        camera_id=obs.camera_id,
        canonical_vehicle_id=obs.canonical_vehicle_id,
        normalized_plate=obs.normalized_plate,
        vehicle_class=obs.vehicle_class,
        timestamp=obs.timestamp,
        plate_read_id=obs.plate_read_id,
        created_at=obs.created_at,
    )


def _compute_attention_state(camera, repos: Repositories):
    try:
        # Pass repos=None to prevent evaluate from executing individual N+1 DB vehicle history queries for all 30 cameras
        res = AttentionEngine.evaluate(camera, repos=None)
        return res.attention_state, res.attention_reason
    except Exception:
        return "NORMAL", None


def _camera_to_response(
    camera,
    attention_state: str = "NORMAL",
    attention_reason: Optional[str] = None,
    ai_active_override: Optional[bool] = None,
) -> CameraResponse:
    cam_id = str(getattr(camera, "camera_id", ""))
    is_ai_active = (
        ai_active_override
        if ai_active_override is not None
        else (getattr(camera, "ai_active", False) if isinstance(camera, NormalizedCamera) else (cam_id == "cam01"))
    )

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
            ai_active=is_ai_active,
            attention_state=attention_state,
            attention_reason=attention_reason,
        )

    res = getattr(camera, "resolution", None)
    if not res and getattr(camera, "width", None) and getattr(camera, "height", None):
        res = f"{camera.width}x{camera.height}"

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
        ai_active=is_ai_active,
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
# Health & Telemetry
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


def _build_camera_health_responses(repos: Repositories) -> List[CameraHealthResponse]:
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
        else:
            cam_map[db_c.camera_id] = db_c

    db_health_list = repos.health.list_health()
    health_map = {h.camera_id: h for h in db_health_list}

    responses: List[CameraHealthResponse] = []
    for cam_id in sorted(cam_map.keys()):
        cam = cam_map[cam_id]
        att_state, att_reason = _compute_attention_state(cam, repos)
        is_ai_active = (cam_id == "cam01")

        h = health_map.get(cam_id)
        status = h.status if h else "NOT_CHECKED"

        responses.append(
            CameraHealthResponse(
                camera_id=cam_id,
                name=getattr(cam, "name", None),
                location=getattr(cam, "location", None),
                status=status,
                last_successful_frame_at=h.last_successful_frame_at if h else None,
                last_attempt_at=h.last_attempt_at if h else None,
                last_failure_at=h.last_failure_at if h else None,
                consecutive_failures=h.consecutive_failures if h else 0,
                reconnect_count=h.reconnect_count if h else 0,
                last_error=h.last_error if h else None,
                ai_active=is_ai_active,
                attention_state=att_state,
                attention_reason=att_reason,
            )
        )
    return responses


@app.get("/api/system/health", response_model=SystemHealthResponse)
def get_system_health(repos: Repositories = Depends(get_repositories)):
    """Full system health summary and camera monitoring list."""
    database_ok = True
    try:
        repos.db.table_names()
    except Exception:
        database_ok = False

    cam_responses = _build_camera_health_responses(repos)

    total = len(cam_responses)
    online_count = sum(1 for c in cam_responses if c.status == "ONLINE")
    degraded_count = sum(1 for c in cam_responses if c.status == "DEGRADED")
    offline_count = sum(1 for c in cam_responses if c.status == "OFFLINE")
    not_checked_count = sum(1 for c in cam_responses if c.status in ("NOT_CHECKED", "UNKNOWN"))
    ai_active_count = sum(1 for c in cam_responses if c.ai_active)

    summary = HealthSummaryCounts(
        total_configured=total,
        online_count=online_count,
        degraded_count=degraded_count,
        offline_count=offline_count,
        not_checked_count=not_checked_count,
        ai_active_count=ai_active_count,
    )

    sys_status = (
        "ok"
        if database_ok and offline_count == 0 and degraded_count == 0
        else ("degraded" if database_ok else "unavailable")
    )

    return SystemHealthResponse(
        status=sys_status,
        database="ok" if database_ok else "unavailable",
        summary=summary,
        cameras=cam_responses,
    )


@app.get("/api/cameras/health", response_model=List[CameraHealthResponse])
def get_cameras_health(repos: Repositories = Depends(get_repositories)):
    """Camera health list endpoint."""
    return _build_camera_health_responses(repos)



# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------
@app.get("/api/cameras", response_model=List[CameraResponse])
def list_cameras(
    selected_camera_id: Optional[str] = Query(None),
    repos: Repositories = Depends(get_repositories),
    user: dict = Depends(get_current_user),
):
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

    active_id = selected_camera_id if selected_camera_id else "cam01"
    db_health_list = repos.health.list_health()
    health_map = {h.camera_id: h.status for h in db_health_list}

    responses = []
    for cam_id, cam in cam_map.items():
        att_state, att_reason = _compute_attention_state(cam, repos)
        is_active = (cam_id == active_id)
        resp = _camera_to_response(
            cam,
            attention_state=att_state,
            attention_reason=att_reason,
            ai_active_override=is_active,
        )
        # Runtime health status takes precedence over static catalogue status
        runtime_status = health_map.get(cam_id)
        if runtime_status is not None:
            resp.status = runtime_status.lower()
            resp.live = (runtime_status == "ONLINE")
        responses.append(resp)

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


@app.get("/api/cameras/{camera_id}/diagnose")
def diagnose_camera_rtsp(
    camera_id: str,
    user: dict = Depends(get_current_user),
):
    """Diagnostic endpoint for Render -> RTSP connectivity verification."""
    import socket, time, cv2
    from backend.camera.rtsp_credentials import (
        ENV_RTSP_EMAIL,
        ENV_RTSP_PASSWORD,
        build_authenticated_rtsp_url,
        configure_rtsp_tcp,
    )

    result = {
        "camera_id": camera_id,
        "env_email_configured": bool(os.environ.get(ENV_RTSP_EMAIL)),
        "env_password_configured": bool(os.environ.get(ENV_RTSP_PASSWORD)),
        "tcp_8554_reachable": False,
        "rtsp_url_built": False,
        "opencv_opened": False,
        "frame_read": False,
        "frame_resolution": None,
        "error": None,
    }

    try:
        # 1. Test TCP socket connection to 103.250.160.189:8554
        try:
            sock = socket.create_connection(("103.250.160.189", 8554), timeout=5.0)
            sock.close()
            result["tcp_8554_reachable"] = True
        except Exception as e:
            result["error"] = f"TCP socket connection to 103.250.160.189:8554 failed: {e}"
            return result

        # 2. Test RTSP URL build
        try:
            url = build_authenticated_rtsp_url(camera_id)
            result["rtsp_url_built"] = True
        except Exception as e:
            result["error"] = f"Failed to build RTSP URL: {e}"
            return result

        # 3. Test OpenCV VideoCapture
        configure_rtsp_tcp()
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            result["opencv_opened"] = True
            ret, frame = cap.read()
            if ret and frame is not None:
                result["frame_read"] = True
                h, w, c = frame.shape
                result["frame_resolution"] = f"{w}x{h}"
            else:
                result["error"] = "VideoCapture opened but frame read failed"
            cap.release()
        else:
            result["error"] = "cv2.VideoCapture(url, cv2.CAP_FFMPEG) failed to open RTSP stream"
    except Exception as top_err:
        result["error"] = f"Top level diagnostic exception: {top_err}"

    return result


@app.get("/api/cameras/{camera_id}/live")
def stream_camera_mjpeg(
    camera_id: str,
    user: dict = Depends(get_current_user),
):
    """Server-side authenticated MJPEG live video relay.

    Streams real camera frames over HTTP multipart/x-mixed-replace.
    RTSP credentials remain server-side inside `rtsp_credentials.py`.
    """
    from fastapi.responses import StreamingResponse
    import cv2, time
    from backend.camera.rtsp_credentials import build_authenticated_rtsp_url, configure_rtsp_tcp

    configure_rtsp_tcp()
    try:
        url = build_authenticated_rtsp_url(camera_id)
    except Exception as err:
        logger.error(f"[MJPEG] Credential error for camera {camera_id}: {err}")
        raise HTTPException(status_code=500, detail=f"RTSP Credential Error: {err}")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        logger.error(f"[MJPEG] OpenCV failed to open RTSP stream for {camera_id}")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to connect to RTSP stream for {camera_id} on 103.250.160.189:8554",
        )

    def frame_generator(capture):
        try:
            last_frame_time = time.time()
            consecutive_fails = 0
            while True:
                ret, frame = capture.read()
                if not ret or frame is None:
                    consecutive_fails += 1
                    if consecutive_fails > 30:
                        break
                    time.sleep(0.05)
                    continue

                consecutive_fails = 0
                now = time.time()
                # Frame rate limiter (~15 fps for network/rendering efficiency)
                if now - last_frame_time < 0.06:
                    time.sleep(0.01)
                    continue
                last_frame_time = now

                # Encode frame to JPEG
                ok, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if not ok:
                    continue

                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
                )
        finally:
            capture.release()

    return StreamingResponse(
        frame_generator(cap),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
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
    user: dict = Depends(require_role("ADMIN")),
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

    # Security Audit Log
    repos.audit.add_audit_entry(
        actor=user.get("username", "system"),
        action="WATCHLIST_CREATE",
        resource_type="watchlist",
        resource_id=created.normalized_plate,
        result="SUCCESS",
        metadata_json=f'{{"category": "{created.category}", "priority": "{created.priority}"}}',
    )

    return _watchlist_to_response(created)


@app.patch("/api/watchlist/{plate}", response_model=WatchlistEntryResponse)
def patch_watchlist_entry(
    plate: str,
    payload: WatchlistEntryUpdate,
    user: dict = Depends(require_role("ADMIN")),
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

    # Security Audit Log
    repos.audit.add_audit_entry(
        actor=user.get("username", "system"),
        action="WATCHLIST_UPDATE",
        resource_type="watchlist",
        resource_id=entry.normalized_plate,
        result="SUCCESS",
    )

    return _watchlist_to_response(entry)


@app.delete("/api/watchlist/{plate}")
def delete_watchlist_entry(
    plate: str,
    user: dict = Depends(require_role("ADMIN")),
    repos: Repositories = Depends(get_repositories),
):
    """Soft-disable a watchlist entry (active=False, no data loss)."""
    try:
        ok = repos.watchlist.deactivate_watchlist_entry(plate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")

    norm = normalize_plate_text(plate)

    # Security Audit Log
    repos.audit.add_audit_entry(
        actor=user.get("username", "system"),
        action="WATCHLIST_DELETE",
        resource_type="watchlist",
        resource_id=norm,
        result="SUCCESS",
    )

    return {
        "detail": "Watchlist entry deactivated",
        "plate": norm,
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
    user: dict = Depends(require_role("OPERATOR")),
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
        # Security Audit Log
        repos.audit.add_audit_entry(
            actor=user.get("username", "system"),
            action="ALERT_STATUS_UPDATE",
            resource_type="alert",
            resource_id=str(alert.id),
            result="SUCCESS",
            metadata_json=f'{{"status": "{alert.status}", "plate": "{alert.normalized_plate}"}}',
        )

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
# Phase 9.10: Cross-Camera Vehicle Tracking Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/vehicles", response_model=GlobalVehicleListResponse)
def list_global_vehicles(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    repos: Repositories = Depends(get_repositories),
):
    """List cross-camera global vehicles ordered by last_seen_at DESC."""
    vehicles = repos.global_vehicles.list_global_vehicles(limit=limit, offset=offset)
    return GlobalVehicleListResponse(
        count=len(vehicles),
        results=[_global_vehicle_to_response(v) for v in vehicles],
    )


@app.get("/api/vehicles/search", response_model=GlobalVehicleResponse)
def search_global_vehicle_by_plate(
    plate: str = Query(..., min_length=1),
    repos: Repositories = Depends(get_repositories),
):
    """Search for a global vehicle identity by raw or normalized plate."""
    gv = repos.global_vehicles.get_global_vehicle_by_plate(plate)
    if gv is None:
        raise HTTPException(status_code=404, detail="Global vehicle not found for plate")
    return _global_vehicle_to_response(gv)


@app.get("/api/vehicles/{global_vehicle_id}", response_model=GlobalVehicleResponse)
def get_global_vehicle(
    global_vehicle_id: str,
    repos: Repositories = Depends(get_repositories),
):
    """Get details for one global vehicle by global_vehicle_id (e.g. GV-000001)."""
    gv = repos.global_vehicles.get_global_vehicle(global_vehicle_id)
    if gv is None:
        # Fallback search by normalized plate if string passes plate format
        gv = repos.global_vehicles.get_global_vehicle_by_plate(global_vehicle_id)
    if gv is None:
        raise HTTPException(status_code=404, detail="Global vehicle not found")
    return _global_vehicle_to_response(gv)


@app.get("/api/vehicles/{global_vehicle_id}/timeline", response_model=GlobalVehicleTimelineResponse)
def get_global_vehicle_timeline(
    global_vehicle_id: str,
    repos: Repositories = Depends(get_repositories),
):
    """Get chronological cross-camera movement timeline for a global vehicle."""
    gv = repos.global_vehicles.get_global_vehicle(global_vehicle_id)
    if gv is None:
        gv = repos.global_vehicles.get_global_vehicle_by_plate(global_vehicle_id)
    if gv is None:
        raise HTTPException(status_code=404, detail="Global vehicle not found")

    timeline = repos.global_vehicles.get_timeline(gv.global_vehicle_id)
    return GlobalVehicleTimelineResponse(
        global_vehicle_id=gv.global_vehicle_id,
        normalized_plate=gv.normalized_plate,
        vehicle_class=gv.vehicle_class,
        first_seen_at=gv.first_seen_at,
        last_seen_at=gv.last_seen_at,
        observation_count=len(timeline),
        timeline=[_observation_to_response(obs) for obs in timeline],
    )


@app.get("/api/vehicles/{global_vehicle_id}/route", response_model=GlobalVehicleRouteResponse)
def get_global_vehicle_route(
    global_vehicle_id: str,
    repos: Repositories = Depends(get_repositories),
):
    """Get geographical movement route for a global vehicle."""
    gv = repos.global_vehicles.get_global_vehicle(global_vehicle_id)
    if gv is None:
        gv = repos.global_vehicles.get_global_vehicle_by_plate(global_vehicle_id)
    if gv is None:
        raise HTTPException(status_code=404, detail="Global vehicle not found")

    route_points = repos.global_vehicles.get_route(gv.global_vehicle_id)
    mapped_count = sum(1 for p in route_points if p["latitude"] is not None and p["longitude"] is not None)

    return GlobalVehicleRouteResponse(
        global_vehicle_id=gv.global_vehicle_id,
        normalized_plate=gv.normalized_plate,
        vehicle_class=gv.vehicle_class,
        first_seen_at=gv.first_seen_at,
        last_seen_at=gv.last_seen_at,
        total_observations=len(route_points),
        mapped_points_count=mapped_count,
        points=[
            RoutePointResponse(
                camera_id=p["camera_id"],
                timestamp=p["timestamp"],
                latitude=p["latitude"],
                longitude=p["longitude"],
                vehicle_class=p["vehicle_class"],
                canonical_vehicle_id=p["canonical_vehicle_id"],
                normalized_plate=p["normalized_plate"],
            )
            for p in route_points
        ],
    )


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
