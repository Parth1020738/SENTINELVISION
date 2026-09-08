"""
SentinelVision - ANPR Engine

Ties together plate detection, OCR, multi-frame aggregation, and
canonical-vehicle association.

Phase 5: ANPR / License Plate Recognition

Responsibilities
----------------
- Accept a frame + list of tracked vehicles (with canonical IDs).
- Detect plates and associate each plate with the best vehicle.
- Run OCR on each matched plate crop.
- Aggregate OCR observations over multiple frames using
  confidence-weighted voting.
- Maintain ONE best plate result per canonical vehicle ID
  (duplicate protection).
- Expose a structured ANPRResult.

The engine depends only on the PlateDetector and PlateOCR
abstract interfaces, so it is fully testable with mocks
without any GPU, camera, or model.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from backend.ai.plate_detector import PlateDetection, PlateDetector
from backend.ai.plate_ocr import (
    PlateOCR,
    normalize_plate_text,
    is_valid_plate_format,
)


# ---------------------------------------------------------------------------
# Input: a tracked vehicle in the current frame
# ---------------------------------------------------------------------------
@dataclass
class VehicleInfo:
    """A vehicle detected by the upstream tracking pipeline (Phases 1-3).

    Attributes
    ----------
    canonical_id : int
        Stable canonical vehicle ID from the Track Continuity Manager.
    bbox : tuple
        Vehicle bounding box (x1, y1, x2, y2).
    class_name : str or None
        Stabilized vehicle class (car, motorcycle, bus, truck).
    """

    canonical_id: int
    bbox: Tuple[float, float, float, float]
    class_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Output: final ANPR result
# ---------------------------------------------------------------------------
@dataclass
class ANPRResult:
    """Structured ANPR result for one canonical vehicle."""

    canonical_vehicle_id: int
    vehicle_class: Optional[str]
    plate_text: str
    plate_detection_confidence: float
    ocr_confidence: float
    combined_confidence: float
    frame_number: Optional[int] = None
    timestamp: Optional[float] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    observation_count: int = 0
    status: str = "PLATE_READ"  # PLATE_READ, PLATE_DETECTED_UNREADABLE, LOW_CONFIDENCE, INVALID_PLATE
    preprocessing_method: str = "bicubic_2x_clahe"
    quality_score: float = 1.0
    crop_dimensions: Optional[Tuple[int, int]] = None


# ---------------------------------------------------------------------------
# Internal state per vehicle
# ---------------------------------------------------------------------------
@dataclass
class _VehiclePlateState:
    """Temporal state maintained per canonical vehicle ID."""

    # text -> list of combined confidences
    observations: Dict[str, List[float]] = field(default_factory=dict)
    # current best result
    best_result: Optional[ANPRResult] = None

# ---------------------------------------------------------------------------
# ANPR Engine
# ---------------------------------------------------------------------------
class ANPREngine:
    """Automatic Number Plate Recognition engine.

    Parameters
    ----------
    plate_detector : PlateDetector
        Plate detection backend (real or mock).
    plate_ocr : PlateOCR
        OCR backend (real or mock).
    min_detection_confidence : float
        Minimum plate detection confidence to consider.
    """

    def __init__(
        self,
        plate_detector: PlateDetector,
        plate_ocr: PlateOCR,
        min_detection_confidence: float = 0.1,
    ) -> None:
        self.detector = plate_detector
        self.ocr = plate_ocr
        self.min_detection_confidence = min_detection_confidence
        self._anpr_attempts = 0
        self._ocr_attempts = 0

        # canonical_id -> _VehiclePlateState
        self._state: Dict[int, _VehiclePlateState] = {}

    def _crop_vehicle_roi(
        self,
        frame: np.ndarray,
        vehicle_bbox: Tuple[float, float, float, float],
        margin_ratio: float = 0.10,
    ) -> Tuple[Optional[np.ndarray], float, float, float]:
        """Crop a vehicle ROI from the frame with bounded expansion and clamping.

        Returns (roi_crop, rx1, ry1, scale_factor)
        """
        h, w = frame.shape[:2]
        vx1, vy1, vx2, vy2 = vehicle_bbox
        vw = max(0.0, vx2 - vx1)
        vh = max(0.0, vy2 - vy1)

        if vw < 15 or vh < 15:
            return None, 0.0, 0.0, 1.0

        # Expand box by margin_ratio
        pad_w = vw * margin_ratio
        pad_h = vh * margin_ratio

        rx1 = max(0, int(round(vx1 - pad_w)))
        ry1 = max(0, int(round(vy1 - pad_h)))
        rx2 = min(w, int(round(vx2 + pad_w)))
        ry2 = min(h, int(round(vy2 + pad_h)))

        rw = rx2 - rx1
        rh = ry2 - ry1

        if rw <= 10 or rh <= 10:
            return None, 0.0, 0.0, 1.0

        crop = frame[ry1:ry2, rx1:rx2]
        if crop is None or crop.size == 0:
            return None, 0.0, 0.0, 1.0

        # Scale ROI up if small so detector receives clear features
        target_w = 640.0
        if rw < target_w:
            scale = target_w / float(rw)
            target_h = int(round(rh * scale))
            import cv2

            crop_scaled = cv2.resize(crop, (int(target_w), target_h))
            return crop_scaled, float(rx1), float(ry1), scale
        else:
            return crop, float(rx1), float(ry1), 1.0

    # ------------------------------------------------------------------
    def process_frame(
        self,
        frame: np.ndarray,
        vehicles: List[VehicleInfo],
        frame_number: int = 0,
        timestamp: Optional[float] = None,
    ) -> List[ANPRResult]:
        """Process one frame for ANPR.

        For each vehicle: ROI crop -> plate detect -> crop -> OCR -> normalize
        -> validate -> update multi-frame aggregation.

        Returns
        -------
        list[ANPRResult]
            Updated best results for vehicles with a new observation
            this frame. Empty list if none.
        """
        if timestamp is None:
            timestamp = time.time()

        if frame is None or frame.size == 0:
            return []

        updated: List[ANPRResult] = []
        all_plates_fallback: Optional[List[PlateDetection]] = None

        for vehicle in vehicles:
            self._anpr_attempts += 1
            # 1. Try vehicle ROI-based plate detection
            roi_crop, rx1, ry1, scale = self._crop_vehicle_roi(frame, vehicle.bbox)
            roi_plates: List[PlateDetection] = []
            if roi_crop is not None and roi_crop.size > 0:
                crop_h, crop_w = roi_crop.shape[:2]
                roi_dets = self.detector.detect(roi_crop)
                for d in roi_dets:
                    # Filter out detections that fall outside the ROI crop bounds
                    if d.x1 > crop_w or d.y1 > crop_h or d.x2 < 0 or d.y2 < 0:
                        continue
                    full_x1 = rx1 + (d.x1 / scale)
                    full_y1 = ry1 + (d.y1 / scale)
                    full_x2 = rx1 + (d.x2 / scale)
                    full_y2 = ry1 + (d.y2 / scale)
                    roi_plates.append(PlateDetection(full_x1, full_y1, full_x2, full_y2, d.confidence))

            plate = self._match_plate_to_vehicle(roi_plates, vehicle.bbox) if roi_plates else None

            # Fallback: full-frame detection if ROI detection yielded nothing (mock/backwards compatibility)
            if plate is None:
                if all_plates_fallback is None:
                    all_plates_fallback = self.detector.detect(frame)
                plate = self._match_plate_to_vehicle(all_plates_fallback, vehicle.bbox)

            if plate is None:
                continue

            if plate.confidence < self.min_detection_confidence:
                continue

            # 2. Crop plate region
            crop = self._crop_plate(frame, plate)
            if crop is None or crop.size == 0:
                continue

            # 3. OCR
            self._ocr_attempts += 1
            ocr_result = self.ocr.recognize(crop)

            # 4. Normalize
            text = normalize_plate_text(ocr_result.text)

            # Reject empty / invalid
            if not text:
                continue
            if not is_valid_plate_format(text):
                continue

            # 5. Combined confidence for this single observation
            combined = plate.confidence * ocr_result.confidence

            # 6. Update aggregation
            result = self._add_observation(
                canonical_id=vehicle.canonical_id,
                text=text,
                combined_confidence=combined,
                det_confidence=plate.confidence,
                ocr_confidence=ocr_result.confidence,
                vehicle_class=vehicle.class_name,
                frame_number=frame_number,
                timestamp=timestamp,
                plate_bbox=(plate.x1, plate.y1, plate.x2, plate.y2),
            )

            if result is not None:
                updated.append(result)

        return updated

    # ------------------------------------------------------------------
    def get_best_plate(self, canonical_id: int) -> Optional[ANPRResult]:
        """Return the current best plate result for a vehicle, or None."""
        state = self._state.get(canonical_id)
        if state is None:
            return None
        return state.best_result

    # ------------------------------------------------------------------
    def get_all_plates(self) -> Dict[int, ANPRResult]:
        """Return a copy of all current best plate results."""
        return {
            cid: state.best_result
            for cid, state in self._state.items()
            if state.best_result is not None
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Clear all temporal state (observations + best results)."""
        self._state.clear()

    # ------------------------------------------------------------------
    # Spatial matching: choose the best plate for a vehicle
    # ------------------------------------------------------------------
    def _match_plate_to_vehicle(
        self,
        plates: List[PlateDetection],
        vehicle_bbox: Tuple[float, float, float, float],
    ) -> Optional[PlateDetection]:
        """Find the best plate detection for a given vehicle.

        Prefers plates that are inside or significantly overlapping
        the vehicle bounding box.  Among candidates, returns the one
        with the highest score (overlap-weighted confidence).

        Returns None if no plate is spatially relevant.
        """
        if not plates:
            return None

        vx1, vy1, vx2, vy2 = vehicle_bbox
        vw = max(0.0, vx2 - vx1)
        vh = max(0.0, vy2 - vy1)
        vcx = (vx1 + vx2) / 2.0
        vcy = (vy1 + vy2) / 2.0

        best_plate: Optional[PlateDetection] = None
        best_score: float = -1.0

        for plate in plates:
            px1, py1, px2, py2 = plate.x1, plate.y1, plate.x2, plate.y2
            pw = max(0.0, px2 - px1)
            ph = max(0.0, py2 - py1)
            p_area = pw * ph

            # Intersection
            ix1 = max(px1, vx1)
            iy1 = max(py1, vy1)
            ix2 = min(px2, vx2)
            iy2 = min(py2, vy2)
            iw = max(0.0, ix2 - ix1)
            ih = max(0.0, iy2 - iy1)
            inter = iw * ih

            if inter > 0:
                # Overlap as fraction of plate area
                plate_overlap = inter / p_area if p_area > 0 else 0.0
                # Score: confidence weighted by how much of the plate
                # sits inside the vehicle box
                score = plate.confidence * plate_overlap
            else:
                # No intersection - check proximity of plate center
                pcx = (px1 + px2) / 2.0
                pcy = (py1 + py2) / 2.0
                dist = np.hypot(pcx - vcx, pcy - vcy)
                # Allow plates slightly outside the vehicle box
                reach = max(vw, vh) * 1.5
                if dist > reach:
                    continue  # too far - reject
                # Near but not overlapping - small score
                proximity = max(0.0, 1.0 - dist / reach)
                score = plate.confidence * proximity * 0.1

            if score > best_score:
                best_score = score
                best_plate = plate

        return best_plate

    # ------------------------------------------------------------------
    # Crop with boundary clamping
    # ------------------------------------------------------------------
    def _crop_plate(
        self,
        frame: np.ndarray,
        plate: PlateDetection,
    ) -> Optional[np.ndarray]:
        """Crop a plate region from the frame with adaptive CLAHE enhancement and upscaling."""
        import cv2

        h, w = frame.shape[:2]
        # Slight margin padding around plate detection to capture full borders
        pw = max(0.0, plate.x2 - plate.x1)
        ph = max(0.0, plate.y2 - plate.y1)
        margin_x = pw * 0.05
        margin_y = ph * 0.05

        x1 = max(0, int(round(plate.x1 - margin_x)))
        y1 = max(0, int(round(plate.y1 - margin_y)))
        x2 = min(w, int(round(plate.x2 + margin_x)))
        y2 = min(h, int(round(plate.y2 + margin_y)))

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2].copy()
        if crop is None or crop.size == 0:
            return None

        crop_h, crop_w = crop.shape[:2]
        # For low-resolution government camera crops (< 120px wide), upscale with bicubic, CLAHE, denoise & sharpen
        if crop_w < 120 or crop_h < 40:
            scale = max(120.0 / float(crop_w), 40.0 / float(crop_h))
            new_w = int(round(crop_w * scale))
            new_h = int(round(crop_h * scale))
            crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

            # 1. Grayscale & CLAHE local contrast enhancement
            if len(crop.shape) == 3:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            else:
                gray = crop.copy()
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
            enhanced_gray = clahe.apply(gray)

            # 2. Mild Denoising
            denoised = cv2.GaussianBlur(enhanced_gray, (3, 3), 0)

            # 3. Controlled Sharpening
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            sharpened = cv2.filter2D(denoised, -1, kernel)

            crop = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

        return crop

    # ------------------------------------------------------------------
    # Multi-frame aggregation with confidence-weighted voting
    # ------------------------------------------------------------------
    def _add_observation(
        self,
        canonical_id: int,
        text: str,
        combined_confidence: float,
        det_confidence: float,
        ocr_confidence: float,
        vehicle_class: Optional[str],
        frame_number: int,
        timestamp: float,
        plate_bbox: Tuple[float, float, float, float],
    ) -> Optional[ANPRResult]:
        """Add one OCR observation and recompute the best plate.

        Uses confidence-weighted voting: each text variant accumulates
        the sum of its combined confidences.  The variant with the
        highest total wins.

        Returns an updated ANPRResult if the best result changed
        (new text, or same text with higher confidence), else None.
        """
        if canonical_id not in self._state:
            self._state[canonical_id] = _VehiclePlateState()

        state = self._state[canonical_id]

        # Record observation
        if text not in state.observations:
            state.observations[text] = []
        state.observations[text].append(combined_confidence)

        # Confidence-weighted voting: total confidence per text
        scores: Dict[str, float] = {
            t: sum(confs) for t, confs in state.observations.items()
        }
        winner = max(scores, key=scores.get)

        # Best single combined confidence seen for the winner
        winner_best_conf = max(state.observations[winner])
        total_observations = sum(len(v) for v in state.observations.values())

        prev = state.best_result

        # Decide whether to update the stored best result
        should_update = False
        if prev is None:
            should_update = True
        elif winner != prev.plate_text:
            # Winner changed
            should_update = True
        elif winner_best_conf > prev.combined_confidence:
            # Same winner, stronger evidence
            should_update = True

        if not should_update:
            # Still sync the observation count on the stored result
            if prev is not None:
                prev.observation_count = total_observations
            return None

        new_result = ANPRResult(
            canonical_vehicle_id=canonical_id,
            vehicle_class=vehicle_class,
            plate_text=winner,
            plate_detection_confidence=det_confidence,
            ocr_confidence=ocr_confidence,
            combined_confidence=winner_best_conf,
            frame_number=frame_number,
            timestamp=timestamp,
            bbox=plate_bbox,
            observation_count=total_observations,
        )

        state.best_result = new_result
        return new_result
