"""
SentinelVision - ANPR Tests

Phase 5: ANPR / License Plate Recognition

Covers: detection structure, OCR structure, normalization,
Indian plate validation, multi-frame aggregation, canonical vehicle
association, duplicate protection, spatial matching, temporal state.
"""

import unittest
import time

import numpy as np

from backend.ai.plate_detector import PlateDetection, PlateDetector
from backend.ai.plate_ocr import (
    PlateOCR,
    PlateOCRResult,
    normalize_plate_text,
    is_valid_plate_format,
)
from backend.ai.anpr_engine import ANPREngine, ANPRResult, VehicleInfo


# ---------------------------------------------------------------------------
# Mock implementations for deterministic, GPU-free testing
# ---------------------------------------------------------------------------
class MockPlateDetector(PlateDetector):
    """Returns pre-configured plate detections."""

    def __init__(self, detections=None):
        self._detections = detections if detections is not None else []

    def detect(self, frame):
        return list(self._detections)


class MockPlateOCR(PlateOCR):
    """Returns pre-configured OCR results in sequence."""

    def __init__(self, results=None, default_text="", default_confidence=0.9):
        self._results = list(results) if results else []
        self._default_text = default_text
        self._default_confidence = default_confidence
        self._call_count = 0

    def recognize(self, crop):
        self._call_count += 1
        if self._call_count <= len(self._results):
            return self._results[self._call_count - 1]
        return PlateOCRResult(
            text=self._default_text,
            confidence=self._default_confidence,
        )

    def add_result(self, text, confidence):
        """Append a result to the queue (convenience for tests)."""
        self._results.append(PlateOCRResult(text=text, confidence=confidence))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_frame(w=640, h=480):
    """Create a blank BGR frame."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def make_engine(detections=None, ocr_text="GJ01AB1234", ocr_conf=0.9):
    """Build an ANPREngine with mock detector + mock OCR."""
    detector = MockPlateDetector(detections=detections or [])
    ocr = MockPlateOCR(default_text=ocr_text, default_confidence=ocr_conf)
    engine = ANPREngine(detector, ocr)
    return engine, detector, ocr


# ---------------------------------------------------------------------------
# Test 1: Plate detection result structure
# ---------------------------------------------------------------------------
class TestPlateDetectionStructure(unittest.TestCase):
    def test_detection_fields(self):
        det = PlateDetection(x1=10, y1=20, x2=100, y2=50, confidence=0.85)
        self.assertEqual(det.x1, 10)
        self.assertEqual(det.y1, 20)
        self.assertEqual(det.x2, 100)
        self.assertEqual(det.y2, 50)
        self.assertEqual(det.confidence, 0.85)

    def test_detection_from_list(self):
        dets = [
            PlateDetection(0, 0, 50, 20, 0.9),
            PlateDetection(100, 100, 200, 150, 0.7),
        ]
        self.assertEqual(len(dets), 2)
        self.assertEqual(dets[1].confidence, 0.7)


# ---------------------------------------------------------------------------
# Test 2: OCR result structure
# ---------------------------------------------------------------------------
class TestOCRResultStructure(unittest.TestCase):
    def test_ocr_result_fields(self):
        res = PlateOCRResult(text="GJ01AB1234", confidence=0.92)
        self.assertEqual(res.text, "GJ01AB1234")
        self.assertEqual(res.confidence, 0.92)


# ---------------------------------------------------------------------------
# Tests 3-6: Text normalization
# ---------------------------------------------------------------------------
class TestTextNormalization(unittest.TestCase):
    def test_basic_normalization(self):
        self.assertEqual(normalize_plate_text("GJ01AB1234"), "GJ01AB1234")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_plate_text(None), "")

    def test_empty_returns_empty(self):
        self.assertEqual(normalize_plate_text(""), "")


class TestLowercaseToUppercase(unittest.TestCase):
    def test_lowercase_converted(self):
        self.assertEqual(normalize_plate_text("gj01ab1234"), "GJ01AB1234")

    def test_mixed_case_converted(self):
        self.assertEqual(normalize_plate_text("Gj01aB1234"), "GJ01AB1234")


class TestSpacesRemoved(unittest.TestCase):
    def test_spaces_removed(self):
        self.assertEqual(normalize_plate_text("GJ 01 AB 1234"), "GJ01AB1234")

    def test_leading_trailing_spaces_removed(self):
        self.assertEqual(normalize_plate_text("  GJ01AB1234  "), "GJ01AB1234")


class TestPunctuationNormalization(unittest.TestCase):
    def test_hyphens_removed(self):
        self.assertEqual(normalize_plate_text("GJ-01-AB-1234"), "GJ01AB1234")

    def test_dots_removed(self):
        self.assertEqual(normalize_plate_text("GJ.01.AB.1234"), "GJ01AB1234")

    def test_mixed_punctuation_removed(self):
        self.assertEqual(normalize_plate_text("GJ-01 AB.1234"), "GJ01AB1234")


# ---------------------------------------------------------------------------
# Test 7: Empty OCR result rejected
# ---------------------------------------------------------------------------
class TestEmptyOCRRejected(unittest.TestCase):
    def test_empty_text_rejected_by_format(self):
        self.assertFalse(is_valid_plate_format(""))

    def test_whitespace_only_rejected(self):
        # Whitespace normalizes to empty, which fails format validation
        normalized = normalize_plate_text("   ")
        self.assertEqual(normalized, "")
        self.assertFalse(is_valid_plate_format(normalized))

# ---------------------------------------------------------------------------
# Test 8: Basic Indian plate format recognition
# ---------------------------------------------------------------------------
class TestIndianPlateFormat(unittest.TestCase):
    def test_gujarat_plate_valid(self):
        self.assertTrue(is_valid_plate_format("GJ01AB1234"))

    def test_maharashtra_plate_valid(self):
        self.assertTrue(is_valid_plate_format("MH12CD3456"))

    def test_delhi_plate_valid(self):
        self.assertTrue(is_valid_plate_format("DL01AB1234"))

    def test_karnataka_plate_valid(self):
        self.assertTrue(is_valid_plate_format("KA05MN7890"))


# ---------------------------------------------------------------------------
# Test 9: Invalid obvious text rejected
# ---------------------------------------------------------------------------
class TestInvalidTextRejected(unittest.TestCase):
    def test_all_letters_rejected(self):
        self.assertFalse(is_valid_plate_format("ABCDEFGH"))

    def test_all_digits_rejected(self):
        self.assertFalse(is_valid_plate_format("12345678"))

    def test_too_short_rejected(self):
        self.assertFalse(is_valid_plate_format("GJ01"))

    def test_garbage_rejected(self):
        self.assertFalse(is_valid_plate_format("!!!@@@"))


# ---------------------------------------------------------------------------
# Test 10: Single OCR observation
# ---------------------------------------------------------------------------
class TestSingleObservation(unittest.TestCase):
    def test_single_observation_produces_result(self):
        plate = PlateDetection(110, 110, 160, 140, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200), class_name="car")]
        results = engine.process_frame(frame, vehicles, frame_number=100)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].plate_text, "GJ01AB1234")
        self.assertEqual(results[0].canonical_vehicle_id, 101)


# ---------------------------------------------------------------------------
# Test 11: Multiple identical OCR observations
# ---------------------------------------------------------------------------
class TestMultipleIdenticalObservations(unittest.TestCase):
    def test_identical_observations_strengthen(self):
        plate = PlateDetection(110, 110, 160, 140, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200), class_name="car")]
        r1 = engine.process_frame(frame, vehicles, frame_number=100)
        self.assertEqual(len(r1), 1)
        # Second identical observation: duplicate protection means no new
        # result is emitted (confidence did not increase), but the
        # observation count still increments internally.
        r2 = engine.process_frame(frame, vehicles, frame_number=105)
        self.assertEqual(len(r2), 0)
        best = engine.get_best_plate(101)
        self.assertEqual(best.plate_text, "GJ01AB1234")
        self.assertEqual(best.observation_count, 2)


# ---------------------------------------------------------------------------
# Test 12: Confidence-weighted voting
# ---------------------------------------------------------------------------
class TestConfidenceWeightedVoting(unittest.TestCase):
    def test_higher_confidence_wins(self):
        plate = PlateDetection(110, 110, 160, 140, 0.9)
        ocr = MockPlateOCR()
        ocr.add_result("GJ01AB1234", 0.9)
        ocr.add_result("GJ01AB1234", 0.8)
        ocr.add_result("GJ01A81234", 0.3)
        engine = ANPREngine(MockPlateDetector([plate]), ocr)
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        for f in [1, 2, 3]:
            engine.process_frame(frame, vehicles, frame_number=f)
        best = engine.get_best_plate(101)
        self.assertEqual(best.plate_text, "GJ01AB1234")


# ---------------------------------------------------------------------------
# Test 13: Noisy OCR corrected by repeated observations
# ---------------------------------------------------------------------------
class TestNoisyOCRCorrected(unittest.TestCase):
    def test_majority_corrects_noise(self):
        plate = PlateDetection(110, 110, 160, 140, 0.85)
        ocr = MockPlateOCR()
        # 3 correct, 1 noisy
        ocr.add_result("GJ01AB1234", 0.9)
        ocr.add_result("GJ01AB1234", 0.85)
        ocr.add_result("GJ01A81234", 0.4)
        ocr.add_result("GJ01AB1234", 0.88)
        engine = ANPREngine(MockPlateDetector([plate]), ocr)
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        for f in [1, 2, 3, 4]:
            engine.process_frame(frame, vehicles, frame_number=f)
        best = engine.get_best_plate(101)
        self.assertEqual(best.plate_text, "GJ01AB1234")

# ---------------------------------------------------------------------------
# Test 14: Best confidence result
# ---------------------------------------------------------------------------
class TestBestConfidenceResult(unittest.TestCase):
    def test_best_confidence_tracked(self):
        plate = PlateDetection(110, 110, 160, 140, 0.9)
        ocr = MockPlateOCR()
        ocr.add_result("GJ01AB1234", 0.5)
        ocr.add_result("GJ01AB1234", 0.95)
        engine = ANPREngine(MockPlateDetector([plate]), ocr)
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        engine.process_frame(frame, vehicles, frame_number=1)
        engine.process_frame(frame, vehicles, frame_number=2)
        best = engine.get_best_plate(101)
        # Best combined confidence should be the higher one
        self.assertGreaterEqual(best.combined_confidence, 0.9 * 0.95)


# ---------------------------------------------------------------------------
# Test 15: Canonical vehicle association
# ---------------------------------------------------------------------------
class TestCanonicalVehicleAssociation(unittest.TestCase):
    def test_plate_associated_with_canonical_id(self):
        plate = PlateDetection(110, 110, 160, 140, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200), class_name="car")]
        engine.process_frame(frame, vehicles, frame_number=100)
        best = engine.get_best_plate(101)
        self.assertIsNotNone(best)
        self.assertEqual(best.canonical_vehicle_id, 101)
        self.assertEqual(best.vehicle_class, "car")


# ---------------------------------------------------------------------------
# Test 16: Multiple canonical vehicles independently tracked
# ---------------------------------------------------------------------------
class TestMultipleVehiclesIndependentlyTracked(unittest.TestCase):
    def test_two_vehicles_separate_tracking(self):
        plate1 = PlateDetection(110, 110, 160, 140, 0.8)
        plate2 = PlateDetection(310, 110, 360, 140, 0.8)
        engine, _, _ = make_engine(
            detections=[plate1, plate2],
            ocr_text="GJ01AB1234",
        )
        # Override OCR to return different text per vehicle
        ocr = MockPlateOCR()
        ocr.add_result("GJ01AB1234", 0.9)
        ocr.add_result("MH12CD3456", 0.9)
        engine.ocr = ocr
        frame = make_frame()
        vehicles = [
            VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200)),
            VehicleInfo(canonical_id=102, bbox=(300, 100, 500, 200)),
        ]
        engine.process_frame(frame, vehicles, frame_number=1)
        best1 = engine.get_best_plate(101)
        best2 = engine.get_best_plate(102)
        self.assertIsNotNone(best1)
        self.assertIsNotNone(best2)
        self.assertEqual(best1.plate_text, "GJ01AB1234")
        self.assertEqual(best2.plate_text, "MH12CD3456")


# ---------------------------------------------------------------------------
# Test 17: Duplicate observation protection
# ---------------------------------------------------------------------------
class TestDuplicateObservationProtection(unittest.TestCase):
    def test_one_result_per_vehicle(self):
        plate = PlateDetection(110, 110, 160, 140, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        for f in range(1, 6):
            engine.process_frame(frame, vehicles, frame_number=f)
        all_plates = engine.get_all_plates()
        # Only one entry per vehicle
        self.assertEqual(len(all_plates), 1)
        self.assertIn(101, all_plates)


# ---------------------------------------------------------------------------
# Test 18: Plate box inside vehicle
# ---------------------------------------------------------------------------
class TestPlateBoxInsideVehicle(unittest.TestCase):
    def test_plate_inside_vehicle_matched(self):
        # Plate fully inside vehicle bbox
        plate = PlateDetection(150, 150, 200, 180, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        results = engine.process_frame(frame, vehicles, frame_number=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].canonical_vehicle_id, 101)

# ---------------------------------------------------------------------------
# Test 19: Plate box outside unrelated vehicle rejected
# ---------------------------------------------------------------------------
class TestPlateBoxOutsideRejected(unittest.TestCase):
    def test_far_plate_not_matched(self):
        plate = PlateDetection(500, 400, 550, 430, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        results = engine.process_frame(frame, vehicles, frame_number=1)
        self.assertEqual(len(results), 0)


# ---------------------------------------------------------------------------
# Test 20: Multiple plate candidates choose relevant candidate
# ---------------------------------------------------------------------------
class TestMultiplePlateCandidates(unittest.TestCase):
    def test_relevant_plate_chosen(self):
        plate_inside = PlateDetection(150, 150, 200, 180, 0.8)
        plate_far = PlateDetection(500, 400, 550, 430, 0.95)
        engine, _, _ = make_engine(detections=[plate_inside, plate_far])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        results = engine.process_frame(frame, vehicles, frame_number=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].canonical_vehicle_id, 101)


# ---------------------------------------------------------------------------
# Test 21: No plate observation handled safely
# ---------------------------------------------------------------------------
class TestNoPlateObservation(unittest.TestCase):
    def test_no_plates_returns_empty(self):
        engine, _, _ = make_engine(detections=[])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        results = engine.process_frame(frame, vehicles, frame_number=1)
        self.assertEqual(len(results), 0)
        self.assertIsNone(engine.get_best_plate(101))

    def test_empty_frame_handled(self):
        engine, _, _ = make_engine()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        results = engine.process_frame(np.array([]), vehicles, frame_number=1)
        self.assertEqual(len(results), 0)

# ---------------------------------------------------------------------------
# Test 22: Missing/invalid confidence handled safely
# ---------------------------------------------------------------------------
class TestInvalidConfidence(unittest.TestCase):
    def test_zero_confidence_plate_rejected(self):
        plate = PlateDetection(150, 150, 200, 180, 0.0)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        results = engine.process_frame(frame, vehicles, frame_number=1)
        self.assertEqual(len(results), 0)


# ---------------------------------------------------------------------------
# Test 23: Final ANPR result structure
# ---------------------------------------------------------------------------
class TestFinalResultStructure(unittest.TestCase):
    def test_result_has_all_fields(self):
        plate = PlateDetection(150, 150, 200, 180, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200), class_name="car")]
        engine.process_frame(frame, vehicles, frame_number=42)
        best = engine.get_best_plate(101)
        self.assertIsInstance(best, ANPRResult)
        self.assertEqual(best.canonical_vehicle_id, 101)
        self.assertEqual(best.vehicle_class, "car")
        self.assertEqual(best.plate_text, "GJ01AB1234")
        self.assertIsNotNone(best.frame_number)
        self.assertIsNotNone(best.timestamp)
        self.assertIsNotNone(best.bbox)
        self.assertGreater(best.observation_count, 0)


# ---------------------------------------------------------------------------
# Test 24: Reset/cleanup of temporal state
# ---------------------------------------------------------------------------
class TestResetCleanup(unittest.TestCase):
    def test_reset_clears_state(self):
        plate = PlateDetection(150, 150, 200, 180, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        engine.process_frame(frame, vehicles, frame_number=1)
        self.assertIsNotNone(engine.get_best_plate(101))
        engine.reset()
        self.assertIsNone(engine.get_best_plate(101))
        self.assertEqual(len(engine.get_all_plates()), 0)


# ---------------------------------------------------------------------------
# Test 25: Same canonical vehicle keeps its best plate result
# ---------------------------------------------------------------------------
class TestBestPlateRetained(unittest.TestCase):
    def test_best_plate_retained_across_frames(self):
        plate = PlateDetection(150, 150, 200, 180, 0.8)
        engine, _, _ = make_engine(detections=[plate])
        frame = make_frame()
        vehicles = [VehicleInfo(canonical_id=101, bbox=(100, 100, 300, 200))]
        engine.process_frame(frame, vehicles, frame_number=100)
        first_best = engine.get_best_plate(101)
        for f in range(101, 110):
            engine.process_frame(frame, vehicles, frame_number=f)
        final_best = engine.get_best_plate(101)
        self.assertEqual(final_best.plate_text, first_best.plate_text)
        self.assertEqual(final_best.canonical_vehicle_id, 101)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main()
