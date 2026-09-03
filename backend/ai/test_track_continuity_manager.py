"""
SentinelVision - Track Continuity Manager Tests
Phase 3: Track Continuity
"""

import unittest

from backend.ai.track_continuity_manager import (
    TrackObservation,
    TrackContinuityManager,
)


def obs(bt_id, cls, x, y, w=60, h=40, frame=0):
    return TrackObservation(
        raw_track_id=bt_id,
        class_name=cls,
        bbox=(x - w / 2, y - h / 2, x + w / 2, y + h / 2),
        center=(x, y),
        frame_number=frame,
    )


class TestNewTrackGetsCanonicalId(unittest.TestCase):
    def test_first_track_gets_start_id(self):
        mgr = TrackContinuityManager(canonical_id_start=100)
        results = mgr.update([obs(1, "car", 200, 200, frame=0)], frame_number=0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].canonical_id, 100)

    def test_second_track_gets_next_id(self):
        mgr = TrackContinuityManager(canonical_id_start=100)
        mgr.update([obs(1, "car", 200, 200, frame=0)], frame_number=0)
        results = mgr.update([obs(2, "car", 600, 400, frame=1)], frame_number=1)
        self.assertEqual(results[0].canonical_id, 101)


class TestSameByteTrackIdSameCanonicalId(unittest.TestCase):
    def test_consistent_canonical_over_frames(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(42, "car", 100, 100, frame=0)], frame_number=0)
        r2 = mgr.update([obs(42, "car", 105, 100, frame=1)], frame_number=1)
        r3 = mgr.update([obs(42, "car", 110, 100, frame=2)], frame_number=2)
        self.assertEqual(r1[0].canonical_id, r2[0].canonical_id)
        self.assertEqual(r2[0].canonical_id, r3[0].canonical_id)


class TestTemporaryDisappearanceReconnection(unittest.TestCase):
    def test_same_bt_id_reconnects(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(42, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(42, "car", 108, 100, frame=2)], frame_number=2)
        self.assertEqual(r1[0].canonical_id, r3[0].canonical_id)
        self.assertTrue(r3[0].is_reconnected)


class TestReconnectionWithChangedByteTrackId(unittest.TestCase):
    def test_new_bt_id_matches_lost_track(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(42, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(57, "car", 108, 100, frame=2)], frame_number=2)
        self.assertEqual(r1[0].canonical_id, r3[0].canonical_id)
        self.assertEqual(r3[0].bytetrack_id, 57)
        self.assertTrue(r3[0].is_reconnected)


class TestRejectionFarUnrelatedVehicle(unittest.TestCase):
    def test_far_vehicle_gets_new_canonical_id(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(42, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(99, "car", 900, 900, frame=2)], frame_number=2)
        self.assertNotEqual(r1[0].canonical_id, r3[0].canonical_id)
        self.assertFalse(r3[0].is_reconnected)


class TestRejectionAfterExcessiveTimeGap(unittest.TestCase):
    def test_expired_lost_track_no_reconnect(self):
        mgr = TrackContinuityManager(grace_period=3)
        r1 = mgr.update([obs(42, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        mgr.update([], frame_number=2)
        mgr.update([], frame_number=3)
        mgr.update([], frame_number=4)
        r2 = mgr.update([obs(57, "car", 104, 100, frame=5)], frame_number=5)
        self.assertNotEqual(r1[0].canonical_id, r2[0].canonical_id)
class TestPositionMatching(unittest.TestCase):
    def test_close_position_scores_higher(self):
        mgr = TrackContinuityManager()
        mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        close = obs(2, "car", 102, 100, frame=2)
        score_close = mgr._match_score(close, mgr._lost[100])
        mgr2 = TrackContinuityManager()
        mgr2.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr2.update([], frame_number=1)
        far = obs(3, "car", 400, 400, frame=2)
        score_far = mgr2._match_score(far, mgr2._lost[100])
        self.assertGreater(score_close, score_far)


class TestDirectionCompatibility(unittest.TestCase):
    def test_same_direction_scores_higher(self):
        mgr = TrackContinuityManager()
        mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([obs(1, "car", 110, 100, frame=1)], frame_number=1)
        mgr.update([obs(1, "car", 120, 100, frame=2)], frame_number=2)
        mgr.update([], frame_number=3)
        same_dir = obs(2, "car", 130, 100, frame=4)
        score_same = mgr._match_score(same_dir, mgr._lost[100])
        opp_dir = obs(3, "car", 104, 100, frame=4)
        score_opp = mgr._match_score(opp_dir, mgr._lost[100])
        self.assertGreater(score_same, score_opp)


class TestSizeCompatibility(unittest.TestCase):
    def test_similar_size_scores_higher(self):
        mgr = TrackContinuityManager()
        mgr.update([obs(1, "car", 100, 100, w=60, h=40, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        similar = obs(2, "car", 104, 100, w=62, h=42, frame=2)
        score_similar = mgr._match_score(similar, mgr._lost[100])
        different = obs(3, "car", 104, 100, w=200, h=150, frame=2)
        score_different = mgr._match_score(different, mgr._lost[100])
        self.assertGreater(score_similar, score_different)


class TestClassCompatibility(unittest.TestCase):
    def test_same_class_reconnects(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(1, "truck", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(2, "truck", 105, 100, frame=2)], frame_number=2)
        self.assertEqual(r1[0].canonical_id, r3[0].canonical_id)

    def test_incompatible_class_rejected(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(1, "truck", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(2, "motorcycle", 105, 100, frame=2)], frame_number=2)
        self.assertNotEqual(r1[0].canonical_id, r3[0].canonical_id)


class TestMotorcycleCarSoftCompatibility(unittest.TestCase):
    def test_motorcycle_to_car_reconnects(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(1, "motorcycle", 100, 100, w=40, h=30, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(2, "car", 104, 100, w=42, h=32, frame=2)], frame_number=2)
        self.assertEqual(r1[0].canonical_id, r3[0].canonical_id)
        self.assertTrue(r3[0].is_reconnected)


class TestMultipleSimultaneousTracks(unittest.TestCase):
    def test_independent_tracks(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        r2 = mgr.update([obs(2, "truck", 500, 500, frame=0)], frame_number=0)
        self.assertNotEqual(r1[0].canonical_id, r2[0].canonical_id)
        r3 = mgr.update([obs(1, "car", 105, 100, frame=1)], frame_number=1)
        r4 = mgr.update([obs(2, "truck", 505, 500, frame=1)], frame_number=1)
        self.assertEqual(r1[0].canonical_id, r3[0].canonical_id)
        self.assertEqual(r2[0].canonical_id, r4[0].canonical_id)


class TestCountedStateInheritance(unittest.TestCase):
    def test_counted_preserved_after_reconnect(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.mark_counted(r1[0].canonical_id)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(2, "car", 104, 100, frame=2)], frame_number=2)
        self.assertTrue(r3[0].counted)
        self.assertEqual(r1[0].canonical_id, r3[0].canonical_id)


class TestLostTrackExpiration(unittest.TestCase):
    def test_lost_track_expires_after_grace_period(self):
        mgr = TrackContinuityManager(grace_period=3)
        mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)  # lost, aged to 1, 1 < 3 -> stays
        self.assertEqual(len(mgr._lost), 1)
        mgr.update([], frame_number=2)  # aged to 2, 2 < 3 -> stays
        self.assertEqual(len(mgr._lost), 1)
        mgr.update([], frame_number=3)  # aged to 3, 3 >= 3 -> expired
        self.assertEqual(len(mgr._lost), 0)


class TestCleanup(unittest.TestCase):
    def test_cleanup_removes_expired(self):
        mgr = TrackContinuityManager(grace_period=5)
        mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)  # lost, aged to 1
        self.assertEqual(mgr.cleanup(), 0)  # still in grace period
        self.assertEqual(len(mgr._lost), 1)
        # Manually advance to expiration threshold
        for lost in mgr._lost.values():
            lost.frames_since_lost = 5
        self.assertEqual(mgr.cleanup(), 1)
        self.assertEqual(len(mgr._lost), 0)


class TestReset(unittest.TestCase):
    def test_reset_clears_all_state(self):
        mgr = TrackContinuityManager()
        mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        mgr.reset()
        self.assertEqual(len(mgr._active), 0)
        self.assertEqual(len(mgr._lost), 0)
        r = mgr.update([obs(5, "car", 200, 200, frame=2)], frame_number=2)
        self.assertEqual(r[0].canonical_id, 100)


class TestCanonicalIdUniqueness(unittest.TestCase):
    def test_unique_ids_for_different_vehicles(self):
        mgr = TrackContinuityManager()
        observations = [obs(i + 1, "car", 100 + i * 400, 100, frame=0) for i in range(10)]
        results = mgr.update(observations, frame_number=0)
        ids = {r.canonical_id for r in results}
        self.assertEqual(len(ids), 10)


class TestNoAccidentalMerging(unittest.TestCase):
    def test_two_close_vehicles_not_merged(self):
        mgr = TrackContinuityManager()
        r1 = mgr.update([obs(1, "car", 100, 100, frame=0)], frame_number=0)
        mgr.update([], frame_number=1)
        r3 = mgr.update([obs(2, "car", 400, 100, frame=2)], frame_number=2)
        self.assertNotEqual(r1[0].canonical_id, r3[0].canonical_id)


if __name__ == "__main__":
    unittest.main()