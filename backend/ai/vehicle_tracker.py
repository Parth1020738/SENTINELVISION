"""
SentinelVision - Vehicle Tracker

Single boundary between SentinelVision code and Ultralytics ByteTrack.
No other module should call model.track() directly.

Phase 1: Detection and Tracking Foundation
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from backend.ai.vehicle_detector import (
    CLASS_NAMES,
    ALLOWED_CLASS_IDS,
    VehicleDetector,
    DEFAULT_CONFIDENCE,
    DEFAULT_IMGSZ,
)


# ---------------------------------------------------------------------------
# ByteTrack configuration path
# ---------------------------------------------------------------------------
BYTE_TRACK_CONFIG = Path(__file__).resolve().parent / "bytetrack_vehicle.yaml"


# ---------------------------------------------------------------------------
# Structured observation returned for each tracked vehicle
# ---------------------------------------------------------------------------
@dataclass
class VehicleObservation:
    """A single tracked vehicle observation in one frame."""

    raw_track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    center: tuple  # (cx, cy)
    frame_number: int


class VehicleTracker:
    """
    Wraps YOLO + ByteTrack tracking and returns structured observations.

    This is the ONLY module that should call model.track().
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        confidence: float = DEFAULT_CONFIDENCE,
        imgsz: int = DEFAULT_IMGSZ,
        track_config: Optional[Path] = None,
    ) -> None:
        self.detector = VehicleDetector(
            model_path=model_path,
            confidence=confidence,
            imgsz=imgsz,
        )
        self.track_config = Path(track_config) if track_config else BYTE_TRACK_CONFIG

        if not self.track_config.exists():
            raise FileNotFoundError(
                f"ByteTrack config not found: {self.track_config}"
            )

        print(f"[VehicleTracker] ByteTrack config: {self.track_config.name}")

    # ------------------------------------------------------------------
    def track(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
    ) -> List[VehicleObservation]:
        """
        Run tracking on a single frame and return structured observations.

        Parameters
        ----------
        frame : numpy.ndarray
            BGR image.
        frame_number : int
            Frame counter for the observation metadata.

        Returns
        -------
        list[VehicleObservation]
            Tracked vehicles in this frame. Empty list if none.
        """
        results = self.detector.model.track(
            source=frame,
            conf=self.detector.confidence,
            imgsz=self.detector.imgsz,
            classes=list(ALLOWED_CLASS_IDS),
            device=self.detector.device,
            persist=True,
            tracker=str(self.track_config),
            verbose=False,
        )

        return self._extract_observations(results[0], frame_number)

    # ------------------------------------------------------------------
    def _extract_observations(
        self,
        results,
        frame_number: int,
    ) -> List[VehicleObservation]:
        """
        Convert raw Ultralytics results into VehicleObservation objects.

        Handles:
        - Frames with no detections (results.boxes is None)
        - Detections without track IDs (boxes.id is None)
        - Classes outside the allowed set (defensive filter)
        """
        observations: List[VehicleObservation] = []

        if results.boxes is None:
            return observations

        boxes = results.boxes

        # boxes.id may be None if ByteTrack has not assigned IDs
        if boxes.id is None:
            return observations

        # Convert to numpy for easier handling
        xyxy = boxes.xyxy.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        track_ids = boxes.id.cpu().numpy().astype(int)

        for i in range(len(track_ids)):
            class_id = int(cls_ids[i])

            # Defensive filter: skip classes outside allowed set
            if class_id not in ALLOWED_CLASS_IDS:
                continue

            bbox = tuple(xyxy[i].tolist())
            x1, y1, x2, y2 = bbox
            center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

            obs = VehicleObservation(
                raw_track_id=int(track_ids[i]),
                class_id=class_id,
                class_name=CLASS_NAMES[class_id],
                confidence=float(confs[i]),
                bbox=bbox,
                center=center,
                frame_number=frame_number,
            )
            observations.append(obs)

        return observations

    # ------------------------------------------------------------------
    def get_device_info(self) -> dict:
        """Return device info from the underlying detector."""
        return self.detector.get_device_info()
