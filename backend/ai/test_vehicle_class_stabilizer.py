"""
SentinelVision - Vehicle Class Stabilizer Tests

Phase 2: Vehicle Class Stabilization

Covers: single observation, stable classes, flicker rejection, confidence
weighting, history limit, multiple tracks, cleanup, remove, reset, invalid
inputs, and genuine class transitions.
"""

import unittest

from backend.ai.vehicle_class_stabilizer import VehicleClassStabilizer


# ---------------------------------------------------------------------------
# Test: single observation
# ---------------------------------------------------------------------------
class TestSingleObservation(unittest.TestCase):
    def test_single_observation_returns_that_class(self):
        s = VehicleClassStabilizer(history_size=12)
        stable_class, score = s.update(track_id=1, class_name="car", confidence=0.9)
        self.assertEqual(stable_class, "car")
        self.assertAlmostEqual(score, 1.0)


# ---------------------------------------------------------------------------
# Test: stable motorcycle
# ---------------------------------------------------------------------------
class TestStableMotorcycle(unittest.TestCase):
    def test_stable_motorcycle(self):
        s = VehicleClassStabilizer(history_size=12)
        for _ in range(8):
            stable_class, score = s.update(1, "motorcycle", 0.90)
        self.assertEqual(stable_class, "motorcycle")
        self.assertGreater(score, 0.9)


# ---------------------------------------------------------------------------
# Test: stable car
# ---------------------------------------------------------------------------
class TestStableCar(unittest.TestCase):
    def test_stable_car(self):
        s = VehicleClassStabilizer(history_size=12)
        for _ in range(8):
            stable_class, score = s.update(1, "car", 0.95)
        self.assertEqual(stable_class, "car")
        self.assertGreater(score, 0.9)


# ---------------------------------------------------------------------------
# Test: motorcycle/car flicker (the key real-world case)
# ---------------------------------------------------------------------------
class TestMotorcycleCarFlicker(unittest.TestCase):
    def test_motorcycle_with_weak_car_flicker(self):
        """The critical case from the task description."""
        s = VehicleClassStabilizer(history_size=12)
        observations = [
            (1, "motorcycle", 0.90),
            (1, "motorcycle", 0.85),
            (1, "car", 0.20),
            (1, "motorcycle", 0.88),
            (1, "motorcycle", 0.91),
        ]
        for tid, cls, conf in observations:
            stable_class, score = s.update(tid, cls, conf)
        self.assertEqual(stable_class, "motorcycle")


# ---------------------------------------------------------------------------
# Test: car/motorcycle flicker
# ---------------------------------------------------------------------------
class TestCarMotorcycleFlicker(unittest.TestCase):
    def test_car_with_weak_motorcycle_flicker(self):
        s = VehicleClassStabilizer(history_size=12)
        observations = [
            (1, "car", 0.92),
            (1, "car", 0.88),
            (1, "motorcycle", 0.25),
            (1, "car", 0.90),
            (1, "car", 0.94),
        ]
        for tid, cls, conf in observations:
            stable_class, score = s.update(tid, cls, conf)
        self.assertEqual(stable_class, "car")



# ---------------------------------------------------------------------------
# Test: confidence weighting
# ---------------------------------------------------------------------------
class TestConfidenceWeighting(unittest.TestCase):
    def test_high_confidence_overrides_low_confidence(self):
        """A high-confidence observation should dominate low-confidence ones."""
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.30)
        s.update(1, "car", 0.30)
        stable_class, _ = s.update(1, "motorcycle", 0.95)
        self.assertEqual(stable_class, "motorcycle")

    def test_low_confidence_does_not_override_high(self):
        """A single low-confidence blip should not flip a stable class."""
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.95)
        s.update(1, "car", 0.95)
        stable_class, _ = s.update(1, "motorcycle", 0.30)
        self.assertEqual(stable_class, "car")


# ---------------------------------------------------------------------------
# Test: history limit
# ---------------------------------------------------------------------------
class TestHistoryLimit(unittest.TestCase):
    def test_history_is_bounded(self):
        s = VehicleClassStabilizer(history_size=5)
        for _ in range(10):
            s.update(1, "car", 0.9)
        self.assertEqual(len(s._history[1]), 5)

    def test_oldest_observations_dropped(self):
        """After exceeding history size, oldest entries are evicted."""
        s = VehicleClassStabilizer(history_size=3)
        s.update(1, "car", 0.9)
        s.update(1, "car", 0.9)
        s.update(1, "car", 0.9)
        # Now overflow -- oldest car should be dropped
        s.update(1, "motorcycle", 0.9)
        self.assertEqual(len(s._history[1]), 3)
        # History should now contain [car, car, motorcycle]
        classes = [cls for cls, _ in s._history[1]]
        self.assertEqual(classes, ["car", "car", "motorcycle"])


# ---------------------------------------------------------------------------
# Test: multiple track IDs
# ---------------------------------------------------------------------------
class TestMultipleTrackIds(unittest.TestCase):
    def test_independent_histories(self):
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.9)
        s.update(1, "car", 0.9)
        s.update(2, "motorcycle", 0.9)
        s.update(2, "motorcycle", 0.9)
        class1, _ = s.get_stable_class(1)
        class2, _ = s.get_stable_class(2)
        self.assertEqual(class1, "car")
        self.assertEqual(class2, "motorcycle")

    def test_three_tracks(self):
        s = VehicleClassStabilizer(history_size=12)
        for _ in range(4):
            s.update(10, "car", 0.9)
            s.update(20, "bus", 0.9)
            s.update(30, "truck", 0.9)
        self.assertEqual(s.get_stable_class(10)[0], "car")
        self.assertEqual(s.get_stable_class(20)[0], "bus")
        self.assertEqual(s.get_stable_class(30)[0], "truck")



# ---------------------------------------------------------------------------
# Test: cleanup
# ---------------------------------------------------------------------------
class TestCleanup(unittest.TestCase):
    def test_cleanup_removes_stale_tracks(self):
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.9)
        s.update(2, "motorcycle", 0.9)
        s.update(3, "bus", 0.9)
        s.cleanup({1, 2})
        self.assertIn(1, s._history)
        self.assertIn(2, s._history)
        self.assertNotIn(3, s._history)

    def test_cleanup_removes_all_when_none_active(self):
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.9)
        s.update(2, "motorcycle", 0.9)
        s.cleanup(set())
        self.assertEqual(len(s._history), 0)


# ---------------------------------------------------------------------------
# Test: remove
# ---------------------------------------------------------------------------
class TestRemove(unittest.TestCase):
    def test_remove_existing_track(self):
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.9)
        result = s.remove(1)
        self.assertTrue(result)
        self.assertNotIn(1, s._history)

    def test_remove_nonexistent_track(self):
        s = VehicleClassStabilizer(history_size=12)
        result = s.remove(999)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Test: reset
# ---------------------------------------------------------------------------
class TestReset(unittest.TestCase):
    def test_reset_clears_all_history(self):
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.9)
        s.update(2, "motorcycle", 0.9)
        s.reset()
        self.assertEqual(len(s._history), 0)

    def test_reset_allows_fresh_start(self):
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "car", 0.9)
        s.reset()
        stable_class, score = s.update(1, "motorcycle", 0.9)
        self.assertEqual(stable_class, "motorcycle")
        self.assertAlmostEqual(score, 1.0)



# ---------------------------------------------------------------------------
# Test: invalid class
# ---------------------------------------------------------------------------
class TestInvalidClass(unittest.TestCase):
    def test_invalid_class_raises(self):
        s = VehicleClassStabilizer(history_size=12)
        with self.assertRaises(ValueError):
            s.update(1, "bicycle", 0.9)

    def test_auto_rickshaw_not_supported(self):
        """COCO has no auto-rickshaw class -- must reject it."""
        s = VehicleClassStabilizer(history_size=12)
        with self.assertRaises(ValueError):
            s.update(1, "auto_rickshaw", 0.9)


# ---------------------------------------------------------------------------
# Test: invalid confidence
# ---------------------------------------------------------------------------
class TestInvalidConfidence(unittest.TestCase):
    def test_confidence_above_one_raises(self):
        s = VehicleClassStabilizer(history_size=12)
        with self.assertRaises(ValueError):
            s.update(1, "car", 1.5)

    def test_confidence_below_zero_raises(self):
        s = VehicleClassStabilizer(history_size=12)
        with self.assertRaises(ValueError):
            s.update(1, "car", -0.1)

    def test_confidence_non_numeric_raises(self):
        s = VehicleClassStabilizer(history_size=12)
        with self.assertRaises(ValueError):
            s.update(1, "car", "high")


# ---------------------------------------------------------------------------
# Test: genuine class transition
# ---------------------------------------------------------------------------
class TestGenuineClassTransition(unittest.TestCase):
    def test_motorcycle_to_car_transition(self):
        """After persistent car evidence, class should become car."""
        s = VehicleClassStabilizer(history_size=12)
        observations = [
            (1, "motorcycle", 0.9),
            (1, "motorcycle", 0.9),
            (1, "motorcycle", 0.9),
            (1, "car", 0.9),
            (1, "car", 0.9),
            (1, "car", 0.9),
            (1, "car", 0.9),
            (1, "car", 0.9),
        ]
        for tid, cls, conf in observations:
            stable_class, score = s.update(tid, cls, conf)
        self.assertEqual(stable_class, "car")

    def test_no_immediate_transition(self):
        """One car frame should NOT immediately flip from motorcycle."""
        s = VehicleClassStabilizer(history_size=12)
        s.update(1, "motorcycle", 0.9)
        s.update(1, "motorcycle", 0.9)
        s.update(1, "motorcycle", 0.9)
        stable_class, _ = s.update(1, "car", 0.9)
        self.assertEqual(stable_class, "motorcycle")

    def test_car_to_bus_transition(self):
        """Genuine transition from car to bus after persistent evidence."""
        s = VehicleClassStabilizer(history_size=12)
        for _ in range(3):
            s.update(1, "car", 0.9)
        for _ in range(5):
            stable_class, _ = s.update(1, "bus", 0.9)
        self.assertEqual(stable_class, "bus")


if __name__ == "__main__":
    unittest.main()
