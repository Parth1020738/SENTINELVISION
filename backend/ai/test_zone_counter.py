"""
SentinelVision - Zone Counter Tests

Phase 4: Zone / Line Vehicle Counting

Covers: clean entry/exit, jitter handling, stopped vehicles,
born inside, disappears inside, direct jump, reversal,
canonical ID continuity, multiple vehicles, per-class counts,
event contents, cleanup, reset, boundary conditions.
"""

import unittest

from backend.ai.zone_counter import (
    ZoneCounter,
    ZoneObservation,
    CountingEvent,
    STATE_OUTSIDE,
    STATE_INSIDE,
    STATE_COUNTED_IN,
    STATE_COUNTED_OUT,
)


ZONE = (500, 400, 1400, 850)


def obs(cid, cls, cx, cy, frame):
    return ZoneObservation(
        canonical_id=cid, vehicle_class=cls,
        center=(cx, cy), frame_number=frame,
    )


def make_counter(**kwargs):
    kwargs.setdefault("zone", ZONE)
    return ZoneCounter(**kwargs)


class TestCleanEntry(unittest.TestCase):
    def test_clean_outside_to_inside_counts_IN(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        event = c.update(obs(1, "car", 900, 600, 3))
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, "IN")
        self.assertEqual(c.get_total_in(), 1)
        self.assertEqual(c.get_total_out(), 0)


class TestCleanExit(unittest.TestCase):
    def test_clean_inside_to_outside_counts_OUT(self):
        c = make_counter()
        c.update(obs(1, "car", 900, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 1600, 600, 3))
        event = c.update(obs(1, "car", 1600, 600, 4))
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, "OUT")
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c.get_total_out(), 1)


class TestCompleteSequence(unittest.TestCase):
    def test_in_then_out(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 1)
        c.update(obs(1, "car", 1600, 600, 4))
        event = c.update(obs(1, "car", 1600, 600, 5))
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, "OUT")
        self.assertEqual(c.get_total_in(), 1)
        self.assertEqual(c.get_total_out(), 1)


class TestJitterHandling(unittest.TestCase):
    def test_jitter_no_double_count(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 1)
        c.update(obs(1, "car", 490, 600, 4))
        c.update(obs(1, "car", 900, 600, 5))
        c.update(obs(1, "car", 900, 600, 6))
        self.assertEqual(c.get_total_in(), 1)
        self.assertEqual(c.get_total_out(), 0)


class TestStoppedVehicle(unittest.TestCase):
    def test_stopped_inside_counts_once(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        for f in range(4, 20):
            c.update(obs(1, "car", 900, 600, f))
        self.assertEqual(c.get_total_in(), 1)
        self.assertEqual(c.get_total_out(), 0)


class TestBornInside(unittest.TestCase):
    def test_born_inside_no_count(self):
        c = make_counter()
        c.update(obs(1, "car", 900, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c.get_total_out(), 0)
        self.assertEqual(len(c.get_events()), 0)


class TestDisappearsInside(unittest.TestCase):
    def test_disappears_inside_no_OUT(self):
        c = make_counter()
        c.update(obs(1, "car", 900, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        self.assertEqual(c.get_total_out(), 0)
        self.assertEqual(len(c.get_events()), 0)
        self.assertEqual(c._vehicle_states[1].state, STATE_INSIDE)


class TestDirectJump(unittest.TestCase):
    def test_outside_jump_no_count(self):
        c = make_counter()
        c.update(obs(1, "car", 100, 200, 1))
        c.update(obs(1, "car", 1600, 900, 2))
        c.update(obs(1, "car", 200, 800, 3))
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c.get_total_out(), 0)
        self.assertEqual(len(c.get_events()), 0)


class TestGenuineReversal(unittest.TestCase):
    def test_genuine_reversal(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 1)
        c.update(obs(1, "car", 1600, 600, 4))
        c.update(obs(1, "car", 1600, 600, 5))
        self.assertEqual(c.get_total_out(), 1)
        c.update(obs(1, "car", 900, 600, 6))
        c.update(obs(1, "car", 900, 600, 7))
        self.assertEqual(c.get_total_in(), 2)
        self.assertEqual(c.get_total_out(), 1)


class TestSameCanonicalId(unittest.TestCase):
    def test_same_id_one_vehicle(self):
        c = make_counter()
        c.update(obs(101, "car", 200, 600, 10))
        c.update(obs(101, "car", 900, 600, 11))
        c.update(obs(101, "car", 900, 600, 12))
        c.update(obs(101, "car", 900, 600, 20))
        c.update(obs(101, "car", 900, 600, 21))
        self.assertEqual(len(c._vehicle_states), 1)
        self.assertEqual(c.get_total_in(), 1)


class TestMultipleVehicles(unittest.TestCase):
    def test_independent_vehicles(self):
        c = make_counter()
        c.update(obs(101, "car", 200, 500, 1))
        c.update(obs(101, "car", 900, 500, 2))
        c.update(obs(101, "car", 900, 500, 3))
        c.update(obs(102, "car", 200, 700, 2))
        c.update(obs(102, "car", 900, 700, 3))
        c.update(obs(102, "car", 900, 700, 4))
        c.update(obs(103, "car", 900, 600, 1))
        c.update(obs(103, "car", 1600, 600, 2))
        c.update(obs(103, "car", 1600, 600, 3))
        self.assertEqual(c.get_total_in(), 2)
        self.assertEqual(c.get_total_out(), 1)
        self.assertEqual(len(c._vehicle_states), 3)


class TestCarCounting(unittest.TestCase):
    def test_car_count(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_class_in("car"), 1)
        self.assertEqual(c.get_class_out("car"), 0)


class TestMotorcycleCounting(unittest.TestCase):
    def test_motorcycle_count(self):
        c = make_counter()
        c.update(obs(1, "motorcycle", 200, 600, 1))
        c.update(obs(1, "motorcycle", 900, 600, 2))
        c.update(obs(1, "motorcycle", 900, 600, 3))
        self.assertEqual(c.get_class_in("motorcycle"), 1)


class TestBusCounting(unittest.TestCase):
    def test_bus_count(self):
        c = make_counter()
        c.update(obs(1, "bus", 200, 600, 1))
        c.update(obs(1, "bus", 900, 600, 2))
        c.update(obs(1, "bus", 900, 600, 3))
        self.assertEqual(c.get_class_in("bus"), 1)


class TestTruckCounting(unittest.TestCase):
    def test_truck_count(self):
        c = make_counter()
        c.update(obs(1, "truck", 200, 600, 1))
        c.update(obs(1, "truck", 900, 600, 2))
        c.update(obs(1, "truck", 900, 600, 3))
        self.assertEqual(c.get_class_in("truck"), 1)


class TestPerClassInCounts(unittest.TestCase):
    def test_per_class_in(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 500, 1))
        c.update(obs(1, "car", 900, 500, 2))
        c.update(obs(1, "car", 900, 500, 3))
        c.update(obs(2, "motorcycle", 200, 700, 1))
        c.update(obs(2, "motorcycle", 900, 700, 2))
        c.update(obs(2, "motorcycle", 900, 700, 3))
        self.assertEqual(c.get_class_in("car"), 1)
        self.assertEqual(c.get_class_in("motorcycle"), 1)
        self.assertEqual(c.get_class_in("bus"), 0)
        self.assertEqual(c.get_class_in("truck"), 0)
        self.assertEqual(c.get_total_in(), 2)


class TestPerClassOutCounts(unittest.TestCase):
    def test_per_class_out(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 500, 1))
        c.update(obs(1, "car", 900, 500, 2))
        c.update(obs(1, "car", 900, 500, 3))
        c.update(obs(1, "car", 1600, 500, 4))
        c.update(obs(1, "car", 1600, 500, 5))
        c.update(obs(2, "truck", 200, 700, 1))
        c.update(obs(2, "truck", 900, 700, 2))
        c.update(obs(2, "truck", 900, 700, 3))
        c.update(obs(2, "truck", 1600, 700, 4))
        c.update(obs(2, "truck", 1600, 700, 5))
        self.assertEqual(c.get_class_out("car"), 1)
        self.assertEqual(c.get_class_out("truck"), 1)
        self.assertEqual(c.get_class_out("motorcycle"), 0)
        self.assertEqual(c.get_class_out("bus"), 0)
        self.assertEqual(c.get_total_out(), 2)


class TestTotalCounts(unittest.TestCase):
    def test_total_counts(self):
        c = make_counter()
        for i, cid in enumerate([1, 2, 3], start=1):
            c.update(obs(cid, "car", 200, 500 + i * 50, 1))
            c.update(obs(cid, "car", 900, 500 + i * 50, 2))
            c.update(obs(cid, "car", 900, 500 + i * 50, 3))
        for i, cid in enumerate([4, 5], start=1):
            c.update(obs(cid, "car", 900, 500 + i * 50, 1))
            c.update(obs(cid, "car", 1600, 500 + i * 50, 2))
            c.update(obs(cid, "car", 1600, 500 + i * 50, 3))
        self.assertEqual(c.get_total_in(), 3)
        self.assertEqual(c.get_total_out(), 2)


class TestEventContents(unittest.TestCase):
    def test_event_fields(self):
        c = make_counter()
        c.update(obs(42, "truck", 200, 600, 100))
        c.update(obs(42, "truck", 900, 600, 101))
        event = c.update(obs(42, "truck", 900, 600, 102))
        self.assertIsNotNone(event)
        self.assertEqual(event.canonical_vehicle_id, 42)
        self.assertEqual(event.vehicle_class, "truck")
        self.assertEqual(event.direction, "IN")
        self.assertEqual(event.frame_number, 102)
        self.assertEqual(event.position, (900, 600))
        self.assertIsInstance(event, CountingEvent)


class TestCleanupStale(unittest.TestCase):
    def test_cleanup_removes_stale(self):
        c = make_counter(stale_threshold=10)
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        removed = c.cleanup(current_frame=20)
        self.assertEqual(removed, 1)
        self.assertEqual(len(c._vehicle_states), 0)


class TestCleanupPreservesActive(unittest.TestCase):
    def test_active_not_cleaned(self):
        c = make_counter(stale_threshold=10)
        c.update(obs(1, "car", 900, 600, 1))
        c.update(obs(1, "car", 900, 600, 5))
        removed = c.cleanup(current_frame=12)
        self.assertEqual(removed, 0)
        self.assertEqual(len(c._vehicle_states), 1)


class TestReset(unittest.TestCase):
    def test_reset(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 1)
        c.reset()
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c.get_total_out(), 0)
        self.assertEqual(len(c._vehicle_states), 0)
        self.assertEqual(len(c.get_events()), 0)


class TestNoDoubleCount(unittest.TestCase):
    def test_repeated_observations_no_double_count(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        for f in range(4, 10):
            c.update(obs(1, "car", 900, 600, f))
        self.assertEqual(c.get_total_in(), 1)
        self.assertEqual(c.get_total_out(), 0)


class TestNoMerging(unittest.TestCase):
    def test_different_ids_not_merged(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 500, 1))
        c.update(obs(2, "car", 200, 700, 1))
        c.update(obs(1, "car", 900, 500, 2))
        c.update(obs(2, "car", 900, 700, 2))
        c.update(obs(1, "car", 900, 500, 3))
        c.update(obs(2, "car", 900, 700, 3))
        self.assertEqual(len(c._vehicle_states), 2)
        self.assertEqual(c.get_total_in(), 2)


class TestClassUpdateNoDuplicate(unittest.TestCase):
    def test_class_update_no_duplicate(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "truck", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 1)
        events = c.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].vehicle_class, "truck")


class TestBoundaryConditions(unittest.TestCase):
    def test_point_on_boundary_is_inside(self):
        c = make_counter()
        c.update(obs(1, "car", 500, 400, 1))
        c.update(obs(1, "car", 500, 400, 2))
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c._vehicle_states[1].state, STATE_INSIDE)

    def test_point_just_outside(self):
        c = make_counter()
        c.update(obs(1, "car", 499, 399, 1))
        c.update(obs(1, "car", 499, 399, 2))
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c._vehicle_states[1].state, STATE_OUTSIDE)

    def test_zone_coordinate_order_normalized(self):
        c = ZoneCounter(zone=(1400, 850, 500, 400))
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c.get_total_in(), 1)


class TestProcessFrame(unittest.TestCase):
    def test_process_frame(self):
        c = make_counter()
        observations = [
            obs(1, "car", 200, 500, 1),
            obs(2, "car", 200, 700, 1),
        ]
        events = c.process_frame(observations)
        self.assertEqual(len(events), 0)
        observations = [
            obs(1, "car", 900, 500, 2),
            obs(2, "car", 900, 700, 2),
        ]
        events = c.process_frame(observations)
        self.assertEqual(len(events), 0)
        observations = [
            obs(1, "car", 900, 500, 3),
            obs(2, "car", 900, 700, 3),
        ]
        events = c.process_frame(observations)
        self.assertEqual(len(events), 2)


class TestInvalidClass(unittest.TestCase):
    def test_invalid_class_raises(self):
        c = make_counter()
        with self.assertRaises(ValueError):
            c.update(obs(1, "bicycle", 200, 600, 1))


class TestInvalidConstructor(unittest.TestCase):
    def test_invalid_confirmation_frames(self):
        with self.assertRaises(ValueError):
            ZoneCounter(zone=ZONE, confirmation_frames=0)

    def test_invalid_stale_threshold(self):
        with self.assertRaises(ValueError):
            ZoneCounter(zone=ZONE, stale_threshold=0)


class TestGetCounts(unittest.TestCase):
    def test_get_counts_structure(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        counts = c.get_counts()
        self.assertIn("total", counts)
        self.assertIn("car", counts)
        self.assertIn("motorcycle", counts)
        self.assertIn("bus", counts)
        self.assertIn("truck", counts)
        self.assertEqual(counts["total"]["IN"], 1)
        self.assertEqual(counts["total"]["OUT"], 0)
        self.assertEqual(counts["car"]["IN"], 1)
        self.assertEqual(counts["car"]["OUT"], 0)


class TestBornInsideThenExits(unittest.TestCase):
    def test_born_inside_exits(self):
        c = make_counter()
        c.update(obs(1, "car", 900, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 1600, 600, 3))
        event = c.update(obs(1, "car", 1600, 600, 4))
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, "OUT")
        self.assertEqual(c.get_total_in(), 0)
        self.assertEqual(c.get_total_out(), 1)


class TestStateTransitions(unittest.TestCase):
    def test_initial_state_outside(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        self.assertEqual(c._vehicle_states[1].state, STATE_OUTSIDE)

    def test_initial_state_inside(self):
        c = make_counter()
        c.update(obs(1, "car", 900, 600, 1))
        self.assertEqual(c._vehicle_states[1].state, STATE_INSIDE)

    def test_state_after_counted_in(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        self.assertEqual(c._vehicle_states[1].state, STATE_COUNTED_IN)

    def test_state_after_counted_out(self):
        c = make_counter()
        c.update(obs(1, "car", 200, 600, 1))
        c.update(obs(1, "car", 900, 600, 2))
        c.update(obs(1, "car", 900, 600, 3))
        c.update(obs(1, "car", 1600, 600, 4))
        c.update(obs(1, "car", 1600, 600, 5))
        self.assertEqual(c._vehicle_states[1].state, STATE_COUNTED_OUT)


if __name__ == "__main__":
    unittest.main()
