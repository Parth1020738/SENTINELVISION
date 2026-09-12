"""
SentinelVision - Camera Catalogue Manager

Phase 9.3: Dynamic Multi-Camera Catalogue & Grid Foundation

This module manages dynamic camera discovery from the official Sentinel Camera Grid:
https://cctv.corp8.cloud/cameras.json

Security & Isolation Rules:
---------------------------
1. Safe metadata ONLY: Camera records returned by this module NEVER contain
   RTSP credentials, usernames, passwords, or authenticated stream URLs.
2. Graceful fallback: Network timeouts, 404/500 errors, or non-JSON payloads
   must never crash the backend.
3. No fake data: If the catalogue is unreachable and no cache exists, return
   empty list or registered DB cameras without inventing fake camera events.
4. Single AI Camera: cam01 remains the single active AI processing pipeline.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.camera.rtsp_credentials import (
    DEFAULT_CATALOGUE_URL,
    fetch_camera_catalogue,
)

logger = logging.getLogger(__name__)


@dataclass
class NormalizedCamera:
    """Safe, credential-free internal representation of a catalogue camera."""

    camera_id: str
    name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinate_source: Optional[str] = None
    coordinate_approximate: Optional[bool] = None
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    resolution: Optional[str] = None
    live: bool = True
    status: str = "online"
    ai_active: bool = False
    attention_state: str = "NORMAL"
    attention_reason: Optional[str] = None
    anpr_capable: bool = True
    department: Optional[str] = None
    district: Optional[str] = None
    tags: Optional[List[str]] = None
    is_virtual: bool = False


class CameraCatalogue:
    """Dynamic discovery and normalization for Sentinel Camera Grid catalogue.

    Features
    --------
    - Timed in-memory caching to avoid redundant HTTP requests.
    - Robust parsing supporting multiple catalogue JSON formats.
    - Complete credential stripping on all camera metadata.
    """

    def __init__(
        self,
        catalogue_url: str = DEFAULT_CATALOGUE_URL,
        ttl_seconds: float = 30.0,
        fetcher=None,
    ) -> None:
        self.catalogue_url = catalogue_url
        self.ttl_seconds = ttl_seconds
        self.fetcher = fetcher
        self._cached_cameras: Dict[str, NormalizedCamera] = {}
        self._last_fetch_time: float = 0.0

    def refresh(self, force: bool = False) -> List[NormalizedCamera]:
        """Fetch and normalize cameras from official catalogue.

        Returns cached list if within TTL unless ``force=True``.
        """
        now = time.time()
        if not force and self._cached_cameras and (now - self._last_fetch_time < self.ttl_seconds):
            return list(self._cached_cameras.values())

        raw_payload = fetch_camera_catalogue(
            catalogue_url=self.catalogue_url,
            timeout=5.0,
            fetcher=self.fetcher,
        )

        if raw_payload is None:
            if not self._cached_cameras:
                official = get_official_30_catalogue()
                self._cached_cameras = {cam.camera_id: cam for cam in official}
                self._last_fetch_time = now
            logger.info("Catalogue fetch returned None; using cached or fallback cameras.")
            return list(self._cached_cameras.values())

        normalized = self._parse_catalogue_payload(raw_payload)
        if normalized:
            self._cached_cameras = {cam.camera_id: cam for cam in normalized}
            self._last_fetch_time = now
        elif not self._cached_cameras:
            official = get_official_30_catalogue()
            self._cached_cameras = {cam.camera_id: cam for cam in official}
            self._last_fetch_time = now

        return list(self._cached_cameras.values())

    def get_cameras(self) -> List[NormalizedCamera]:
        """Return all discovered catalogue cameras."""
        return self.refresh(force=False)

    def get_camera(self, camera_id: str) -> Optional[NormalizedCamera]:
        """Lookup single discovered camera by ID."""
        cameras = self.get_cameras()
        for cam in cameras:
            if cam.camera_id == camera_id:
                return cam
        return None

    def _parse_catalogue_payload(self, payload: Any) -> List[NormalizedCamera]:
        """Parse dict/list catalogue payload into NormalizedCamera objects.

        Tolerates multiple schema variants:
        - List of dicts: ``[{"id": "cam01", ...}]`` or ``[{"camera_id": "cam01", ...}]``
        - Wrapped object: ``{"cameras": [...]}`` or ``{"data": [...]}`` or ``{"items": [...]}``
        - Key-value object: ``{"cam01": {"name": "..."}, "cam02": {...}}``
        """
        entries: List[Dict[str, Any]] = []

        if isinstance(payload, list):
            entries = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            for key in ("cameras", "camera", "items", "data", "results"):
                val = payload.get(key)
                if isinstance(val, list):
                    entries = [item for item in val if isinstance(item, dict)]
                    break

            if not entries:
                # Check if payload is a dict mapping camera_id -> camera info dict
                for k, v in payload.items():
                    if isinstance(v, dict):
                        item = dict(v)
                        if "id" not in item and "camera_id" not in item:
                            item["camera_id"] = str(k)
                        entries.append(item)

        result: List[NormalizedCamera] = []
        seen_ids = set()

        for entry in entries:
            raw_id = entry.get("id") or entry.get("camera_id") or entry.get("cameraId")
            if not raw_id:
                continue

            cam_id = str(raw_id).strip()
            if not cam_id or cam_id in seen_ids:
                continue
            seen_ids.add(cam_id)

            name = entry.get("name") or entry.get("label") or entry.get("title") or f"Camera {cam_id}"
            location = entry.get("location") or entry.get("site") or entry.get("description")
            
            lat = self._safe_float(entry.get("latitude") or entry.get("lat"))
            lon = self._safe_float(entry.get("longitude") or entry.get("lng") or entry.get("lon"))

            width = self._safe_int(entry.get("width"))
            height = self._safe_int(entry.get("height"))

            resolution = entry.get("resolution")
            if not resolution and width and height:
                resolution = f"{width}x{height}"

            codec = entry.get("codec") or "H264"
            live_val = entry.get("live", True)
            if isinstance(live_val, str):
                live_val = live_val.lower() in ("true", "1", "yes", "online", "live")
            else:
                live_val = bool(live_val)

            status_str = entry.get("status") or entry.get("availability") or ("online" if live_val else "offline")

            # Enforce AI active logic: cam01 is active AI pipeline, others inactive
            ai_active = (cam_id == "cam01")

            dept = entry.get("department") or entry.get("dept")
            dist = entry.get("district") or entry.get("city")
            tags = entry.get("tags") if isinstance(entry.get("tags"), list) else None
            anpr = entry.get("anpr_capable", True)
            if isinstance(anpr, str):
                anpr = anpr.lower() in ("true", "1", "yes")

            result.append(
                NormalizedCamera(
                    camera_id=cam_id,
                    name=str(name) if name else None,
                    location=str(location) if location else None,
                    latitude=lat,
                    longitude=lon,
                    codec=str(codec) if codec else None,
                    width=width,
                    height=height,
                    resolution=str(resolution) if resolution else None,
                    live=live_val,
                    status=str(status_str),
                    ai_active=ai_active,
                    attention_state="NORMAL",
                    anpr_capable=bool(anpr),
                    department=str(dept) if dept else None,
                    district=str(dist) if dist else None,
                    tags=tags,
                )
            )

        return result

    @staticmethod
    def _safe_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val: Any) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None


import os

VIRTUAL_CAMERA_MAP: Dict[str, Dict[str, Any]] = {
    "v_cam01": {
        "name": "v_cam01 (ANPR & License Plate OCR Demo)",
        "location": "Virtual Demo Stream - 4K ANPR Feed",
        "video_path": os.path.join("videos", "Automatic Number Plate Recognition (ANPR) _ Real-Time License Plate Detection & Recognition part 1_2160p.mp4"),
        "latitude": None,
        "longitude": None,
        "district": "Demo Zone",
        "tags": ["DEMO", "VIRTUAL", "ANPR", "OCR"],
    },
    "v_cam02": {
        "name": "v_cam02 (Highway Tracking & Zone Count)",
        "location": "Virtual Demo Stream - Highway Junction",
        "video_path": os.path.join("videos", "Crazy Tata Punch Crash on Highway Caught On Dashcam Video 😳 - Bad Drivers of India (720p, h264).mp4"),
        "latitude": None,
        "longitude": None,
        "district": "Demo Zone",
        "tags": ["DEMO", "VIRTUAL", "TRACKING", "ZONE_COUNTER"],
    },
    "v_cam03": {
        "name": "v_cam03 (Low-Quality CCTV Reference)",
        "location": "Virtual Demo Stream - Standard CCTV",
        "video_path": os.path.join("videos", "License Plate Detection Test - Dev Drone Bhowmik (1080p, h264).mp4"),
        "latitude": None,
        "longitude": None,
        "district": "Demo Zone",
        "tags": ["DEMO", "VIRTUAL", "LOW_QUALITY_CCTV"],
    },
    "v_cam04": {
        "name": "v_cam04 (Urban Multi-Class Traffic Flow)",
        "location": "Virtual Demo Stream - Urban Intersection",
        "video_path": os.path.join("videos", "Traffic in Gujarat is rather orderly... by Indian standards! - WildFilmsIndia (1080p, h264).mp4"),
        "latitude": None,
        "longitude": None,
        "district": "Demo Zone",
        "tags": ["DEMO", "VIRTUAL", "MULTI_CLASS", "URBAN_TRAFFIC"],
    },
    "v_cam05": {
        "name": "v_cam05 (Cross-Camera Gate A - HR19R6697)",
        "location": "Virtual Demo Stream - Entry Gate A",
        "video_path": os.path.join("testdata", "phase_n_same_vehicle", "camera_a.mp4"),
        "latitude": None,
        "longitude": None,
        "district": "Demo Zone",
        "tags": ["DEMO", "VIRTUAL", "CROSS_CAMERA", "GATE_A"],
    },
    "v_cam06": {
        "name": "v_cam06 (Cross-Camera Gate B - HR19R6697)",
        "location": "Virtual Demo Stream - Exit Gate B",
        "video_path": os.path.join("testdata", "phase_n_same_vehicle", "camera_b.mp4"),
        "latitude": None,
        "longitude": None,
        "district": "Demo Zone",
        "tags": ["DEMO", "VIRTUAL", "CROSS_CAMERA", "GATE_B"],
    },
}


def get_virtual_video_path(camera_id: str) -> Optional[str]:
    """Resolve physical video path for a virtual camera ID if file exists."""
    if not camera_id or not str(camera_id).startswith("v_cam"):
        return None

    if camera_id in VIRTUAL_CAMERA_MAP:
        path = VIRTUAL_CAMERA_MAP[camera_id]["video_path"]
        if os.path.exists(path):
            return path

    return None


def get_official_30_catalogue() -> List[NormalizedCamera]:
    """Return neutral fallback catalogue for cam01 through cam30 when remote JSON is unreachable."""
    cams: List[NormalizedCamera] = []
    for i in range(1, 31):
        cam_id = f"cam{i:02d}"
        cams.append(
            NormalizedCamera(
                camera_id=cam_id,
                name=f"Camera {cam_id}",
                location=None,
                codec="H264",
                width=1920,
                height=1080,
                resolution="1920x1080",
                live=True,
                status="online",
                ai_active=(cam_id == "cam01"),
                attention_state="NORMAL",
                is_virtual=False,
            )
        )
    return cams


def get_virtual_30_catalogue() -> List[NormalizedCamera]:
    """Return dynamic virtual demo catalogue ONLY for video files that actually exist on disk."""
    cams: List[NormalizedCamera] = []

    for v_id, info in VIRTUAL_CAMERA_MAP.items():
        vpath = info["video_path"]
        if os.path.exists(vpath):
            cams.append(
                NormalizedCamera(
                    camera_id=v_id,
                    name=info["name"],
                    location=info["location"],
                    latitude=None,
                    longitude=None,
                    coordinate_source=None,
                    coordinate_approximate=False,
                    codec="H264",
                    width=1920,
                    height=1080,
                    resolution="1920x1080",
                    live=True,
                    status="DEMO",
                    ai_active=False,
                    attention_state="NORMAL",
                    anpr_capable=True,
                    department="DEMO",
                    district=info.get("district", "Demo Zone"),
                    tags=info.get("tags", ["DEMO", "VIRTUAL"]),
                    is_virtual=True,
                )
            )
    return cams


get_virtual_catalogue = get_virtual_30_catalogue


# Global catalogue instance for backend API reuse
global_catalogue = CameraCatalogue()
