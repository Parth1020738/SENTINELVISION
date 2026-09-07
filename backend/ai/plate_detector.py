"""
SentinelVision - Plate Detector

Abstract interface for license plate detection plus a YOLO adapter
that connects to a real trained plate model when one is available.

Phase 5: ANPR / License Plate Recognition

Design notes
------------
- The detector returns structured PlateDetection objects.
- The detector knows nothing about database, FastAPI, dashboard,
  watchlist, or GIS.
- YoloPlateDetector requires a real model file. It does NOT invent
  detections when no model is present.
- For testing, inject a mock that implements PlateDetector.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Structured detection result
# ---------------------------------------------------------------------------
@dataclass
class PlateDetection:
    """A single license plate detection in a frame.

    Attributes
    ----------
    x1, y1, x2, y2 : float
        Bounding box coordinates in pixel space.
    confidence : float
        Detection confidence in [0, 1].
    """

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------
class PlateDetector(ABC):
    """Abstract interface for license plate detection.

    Any object that implements ``detect(frame) -> list[PlateDetection]``
    satisfies this interface.  Real implementations may use YOLO,
    PaddleDet, or any other backend.
    """

    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[PlateDetection]:
        """Detect license plates in a frame.

        Parameters
        ----------
        frame : np.ndarray
            BGR image (as read by OpenCV).

        Returns
        -------
        list[PlateDetection]
            Detected license plates. Empty list if none found.
        """
        ...


# ---------------------------------------------------------------------------
# YOLO adapter — real implementation, requires a trained model
# ---------------------------------------------------------------------------
class YoloPlateDetector(PlateDetector):
    """YOLO-based plate detector adapter.

    Requires a trained YOLO license-plate detection model (e.g. a
    ``best.pt`` fine-tuned on license plates).

    This is a real adapter: it does NOT pretend to detect plates when
    no model is available.  If the model file is missing it raises
    ``FileNotFoundError`` immediately at construction time.

    Parameters
    ----------
    model_path : Path
        Path to a YOLO plate detection model (``.pt`` file).
    confidence : float
        Minimum detection confidence threshold.
    imgsz : int
        Inference image size.
    """

    def __init__(
        self,
        model_path,
        confidence: float = 0.2,
        imgsz: int = 960,
    ) -> None:
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.imgsz = imgsz

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Plate detection model not found: {self.model_path}. "
                "A trained YOLO license-plate model is required for "
                "real ANPR.  For testing, inject a mock PlateDetector."
            )

        self._load_model()

    # ------------------------------------------------------------------
    def _load_model(self) -> None:
        """Load the YOLO model from disk."""
        from ultralytics import YOLO

        self.model = YOLO(str(self.model_path))
        print(f"[YoloPlateDetector] Model loaded: {self.model_path.name}")
        print(f"[YoloPlateDetector] Confidence threshold: {self.confidence}")
        print(f"[YoloPlateDetector] Image size: {self.imgsz}")

    # ------------------------------------------------------------------
    def detect(self, frame: np.ndarray) -> List[PlateDetection]:
        """Run YOLO inference and return structured plate detections."""
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            imgsz=self.imgsz,
            verbose=False,
        )

        detections: List[PlateDetection] = []
        r = results[0]

        if r.boxes is None:
            return detections

        xyxy = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()

        for i in range(len(confs)):
            detections.append(
                PlateDetection(
                    x1=float(xyxy[i][0]),
                    y1=float(xyxy[i][1]),
                    x2=float(xyxy[i][2]),
                    y2=float(xyxy[i][3]),
                    confidence=float(confs[i]),
                                )
            )

        return detections


# ---------------------------------------------------------------------------
# Real-model path + factory
# ---------------------------------------------------------------------------
# Default location for the lightweight real license-plate detection model
# (66777yui/yolov8-license-plate-detection, YOLOv8n, ~6 MB, MIT).
DEFAULT_PLATE_MODEL_URL = (
    "https://huggingface.co/66777yui/yolov8-license-plate-"
    "detection/resolve/main/best.pt"
)
DEFAULT_PLATE_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "models" / "plate" / "yolov8n-license-plate.pt"
)


def download_plate_model(
    dest: Optional[Path] = None,
    url: str = DEFAULT_PLATE_MODEL_URL,
    force: bool = False,
) -> Path:
    """Download the real YOLOv8n license-plate detection model (~6 MB).

    Uses only the standard library so it works without ``huggingface_hub``.
    Skips the download if the file already exists (unless ``force=True``).
    """
    dest = Path(dest) if dest is not None else DEFAULT_PLATE_MODEL_PATH
    if dest.exists() and not force:
        print(f"[plate_detector] Model already present: {dest}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request

    print(f"[plate_detector] Downloading real plate model (~6 MB) from {url}")
    urllib.request.urlretrieve(url, str(dest))
    print(
        f"[plate_detector] Saved {dest.name} "
        f"({dest.stat().st_size} bytes)"
    )
    return dest


def build_real_plate_detector(
    model_path: Optional[Path] = None,
    confidence: float = 0.10,
    imgsz: int = 960,
) -> "YoloPlateDetector":
    """Construct a real YOLO plate detector.

    Downloads the lightweight real model automatically if it is not present
    locally.  The detector runs on the GPU when CUDA is available via
    Ultralytics/YOLO.
    """
    if model_path is None:
        model_path = DEFAULT_PLATE_MODEL_PATH
    model_path = Path(model_path)
    if not model_path.exists():
        download_plate_model(model_path)
    return YoloPlateDetector(model_path, confidence=confidence, imgsz=imgsz)
