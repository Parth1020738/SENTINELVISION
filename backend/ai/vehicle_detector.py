"""
SentinelVision - Vehicle Detector

Single source of truth for YOLO detector configuration.
Future modules import configuration from this module.

Phase 1: Detection and Tracking Foundation
"""

from pathlib import Path
from typing import Optional

import torch


# ---------------------------------------------------------------------------
# COCO class mapping for the four vehicle categories SentinelVision tracks.
# ---------------------------------------------------------------------------
CLASS_NAMES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

ALLOWED_CLASS_IDS = set(CLASS_NAMES.keys())


# ---------------------------------------------------------------------------
# Default configuration values
# ---------------------------------------------------------------------------
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "yolo11m.pt"
DEFAULT_CONFIDENCE = 0.20  # Low threshold to preserve weak motorcycle detections
DEFAULT_IMGSZ = 1280  # Camera is 1920x1080; motorcycles may be small/distant


class VehicleDetector:
    """
    Wraps a Ultralytics YOLO model and exposes a single reusable detection
    interface.

    Responsibilities
    ----------------
    * Locate and load the YOLO model.
    * Select CUDA when available, otherwise fall back to CPU.
    * Store the confidence threshold, image size, and allowed class IDs.
    * Expose :meth:`detect` for raw inference results.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        confidence: float = DEFAULT_CONFIDENCE,
        imgsz: int = DEFAULT_IMGSZ,
    ) -> None:
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.confidence = confidence
        self.imgsz = imgsz

        # Device selection
        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.gpu_name = torch.cuda.get_device_name(0)
        else:
            self.device = "cpu"
            self.gpu_name = "CPU (no CUDA)"

        # Load model
        self._load_model()

    # ------------------------------------------------------------------
    def _load_model(self) -> None:
        """Load the YOLO model from disk."""
        from ultralytics import YOLO

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"YOLO model not found: {self.model_path}"
            )

        self.model = YOLO(str(self.model_path))
        print(f"[VehicleDetector] Model loaded: {self.model_path.name}")
        print(f"[VehicleDetector] Device: {self.device} ({self.gpu_name})")
        print(f"[VehicleDetector] Confidence threshold: {self.confidence}")
        print(f"[VehicleDetector] Image size: {self.imgsz}")
        print(f"[VehicleDetector] Allowed classes: {CLASS_NAMES}")

    # ------------------------------------------------------------------
    def detect(self, frame):
        """
        Run YOLO inference on a single frame.

        Parameters
        ----------
        frame : numpy.ndarray
            BGR image (as read by OpenCV).

        Returns
        -------
        ultralytics.engine.results.Results
            Raw YOLO results object.
        """
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            imgsz=self.imgsz,
            classes=list(ALLOWED_CLASS_IDS),
            device=self.device,
            verbose=False,
        )
        return results[0]

    # ------------------------------------------------------------------
    def get_device_info(self) -> dict:
        """Return a dict describing the selected compute device."""
        return {
            "device": self.device,
            "gpu_name": self.gpu_name,
            "cuda_available": torch.cuda.is_available(),
        }
