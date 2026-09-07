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
from typing import Any, Dict, List, Optional

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
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    resolution: Optional[str] = None
    live: bool = True
    status: str = "online"
    ai_active: bool = False
    attention_state: str = "NORMAL"
    attention_reason: Optional[str] = None


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
            logger.info("Catalogue fetch returned None; using cached or fallback cameras.")
            return list(self._cached_cameras.values())

        normalized = self._parse_catalogue_payload(raw_payload)
        if normalized:
            self._cached_cameras = {cam.camera_id: cam for cam in normalized}
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


# Global catalogue instance for backend API reuse
global_catalogue = CameraCatalogue()
