"""
SentinelVision - Alert Engine Tests

Phase 7: deterministic tests for the watchlist alert engine on a
temporary SQLite database.  No GPU / RTSP / internet / YOLO / real
credentials.

Run:  python -m backend.services.test_alert_engine -v
"""

import os
import tempfile
import unittest

from backend.db.database import Database
from backend.db.models import Camera, PlateRead, WatchlistEntry
from backend.db.repositories import (
    AlertRepository,
    CameraRepository,
    PlateRepository,
    WatchlistRepository,
)
from backend.services.alert_engine import AlertEngine

T0 = "2026-01-01T00:00:00+00:00"


def _ts(seconds: int) -> str:
    """ISO timestamp T0 + *seconds*."""
    import datetime

    base = datetime.datetime.fromisoformat(T0)
    return (base + datetime.timedelta(seconds=seconds)).isoformat()


class AlertEngineTestCase(unittest.TestCase):
    """Shared fixture: temp database + watchlist entry + engine."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._tmpdir.name, "test.db"))
        self.db.initialize()
        self.watchlist = WatchlistRepository(self.db)
        self.alerts = AlertRepository(self.db)
        self.cameras = CameraRepository(self.db)
        self.engine = AlertEngine(db=self.db, cooldown_seconds=60.0)
        self.cameras.upsert_camera(Camera(camera_id="cam01", name="Gate 1"))
        self.cameras.upsert_camera(Camera(camera_id="cam02", name="Gate 2"))
        self.plates = PlateRepository(self.db)

    def tearDown(self):
        self._tmpdir.cleanup()

    def add_watch(self, plate="GJ01AB1234", **kwargs):
        entry = WatchlistEntry(
            normalized_plate=plate,
            reason=kwargs.get("reason", "Reported stolen vehicle"),
            category=kwargs.get("category", "STOLEN"),
            priority=kwargs.get("priority", "HIGH"),
            notes=kwargs.get("notes", None),
            active=kwargs.get("active", True),
        )
        entry.id = self.watchlist.add_watchlist_entry(entry)
        return entry

    def process(self, plate="GJ01AB1234", **kwargs):
        return self.engine.process_plate_read(
            plate=plate,
            canonical_vehicle_id=kwargs.get("canonical_vehicle_id", 123),
            camera_id=kwargs.get("camera_id", "cam01"),
            plate_read_id=kwargs.get("plate_read_id"),
            vehicle_class=kwargs.get("vehicle_class", "car"),
            confidence=kwargs.get("confidence", 0.91),
            timestamp=kwargs.get("timestamp", T0),
        )


class TestAlertEngine(AlertEngineTestCase):
    # 12. matching plate generates alert
    def test_matching_plate_generates_alert(self):
        self.add_watch()
        alert = self.process()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.status, "NEW")

    # 13. non-watchlist plate does not
    def test_non_watchlist_plate_does_not(self):
        self.assertIsNone(self.process(plate="MH99ZZ9999"))

    # 14. inactive watchlist plate does not
    def test_inactive_watchlist_plate_does_not(self):
        self.add_watch(active=False)
        self.assertIsNone(self.process())

    # 15. correct reason copied
    def test_reason_copied(self):
        self.add_watch(reason="Reported stolen vehicle")
        alert = self.process()
        self.assertEqual(alert.reason, "Reported stolen vehicle")

    # 16. correct category copied
    def test_category_copied(self):
        self.add_watch(category="STOLEN")
        alert = self.process()
        self.assertEqual(alert.category, "STOLEN")

    # 17. correct priority copied
    def test_priority_copied(self):
        self.add_watch(priority="CRITICAL")
        alert = self.process()
        self.assertEqual(alert.priority, "CRITICAL")

    # 18. camera stored
    def test_camera_stored(self):
        self.add_watch()
        alert = self.process(camera_id="cam02")
        self.assertEqual(alert.camera_id, "cam02")

    # 19. canonical ID stored
    def test_canonical_id_stored(self):
        self.add_watch()
        alert = self.process(canonical_vehicle_id=777)
        self.assertEqual(alert.canonical_vehicle_id, 777)

    # 20. vehicle class stored
    def test_vehicle_class_stored(self):
        self.add_watch()
        alert = self.process(vehicle_class="truck")
        self.assertEqual(alert.vehicle_class, "truck")

    # 21. confidence stored
    def test_confidence_stored(self):
        self.add_watch()
        alert = self.process(confidence=0.87)
        self.assertEqual(alert.confidence, 0.87)

    # 22. timestamp stored
    def test_timestamp_stored(self):
        self.add_watch()
        alert = self.process(timestamp=_ts(5))
        self.assertEqual(alert.timestamp, _ts(5))

    # 23. duplicate same-frame/event suppressed
    def test_duplicate_same_event_suppressed(self):
        self.add_watch()
        first = self.process()
        second = self.process()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.alerts.list_alerts()), 1)

    # 24. duplicate inside cooldown suppressed
    def test_duplicate_inside_cooldown_suppressed(self):
        self.add_watch()
        first = self.process(timestamp=T0)
        second = self.process(timestamp=_ts(30))
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.alerts.list_alerts()), 1)

    # 25. same plate after cooldown can alert again
    def test_same_plate_after_cooldown_can_alert_again(self):
        self.add_watch()
        first = self.process(timestamp=T0)
        second = self.process(timestamp=_ts(61))
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(self.alerts.list_alerts()), 2)

    # 26. different vehicle may alert
    def test_different_vehicle_may_alert(self):
        self.add_watch()
        first = self.process(canonical_vehicle_id=1, timestamp=T0)
        second = self.process(canonical_vehicle_id=2, timestamp=_ts(5))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(self.alerts.list_alerts()), 2)

    # 27. different camera may alert
    def test_different_camera_may_alert(self):
        self.add_watch()
        first = self.process(camera_id="cam01", timestamp=T0)
        second = self.process(camera_id="cam02", timestamp=_ts(5))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(self.alerts.list_alerts()), 2)

    # 28. empty plate safely ignored
    def test_empty_plate_safely_ignored(self):
        self.add_watch()
        self.assertIsNone(self.process(plate=None))
        self.assertIsNone(self.process(plate=""))
        self.assertIsNone(self.process(plate="   --  "))
        self.assertEqual(self.alerts.list_alerts(), [])

    def test_missing_vehicle_or_camera_safely_ignored(self):
        self.add_watch()
        self.assertIsNone(self.process(canonical_vehicle_id=None))
        self.assertIsNone(self.process(camera_id=None))
        self.assertEqual(self.alerts.list_alerts(), [])

    # 29. normalization match works
    def test_normalization_match_works(self):
        self.add_watch("GJ01AB1234")
        alert = self.process(plate="GJ 01 AB 1234")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.normalized_plate, "GJ01AB1234")

    # configurable cooldown
    def test_custom_cooldown_window(self):
        engine = AlertEngine(db=self.db, cooldown_seconds=10.0)
        self.engine = engine
        self.add_watch()
        first = self.process(timestamp=T0)
        inside = self.process(timestamp=_ts(10))
        after = self.process(timestamp=_ts(11))
        self.assertEqual(first.id, inside.id)
        self.assertNotEqual(first.id, after.id)

    # deactivated after creation -> no re-alert
    def test_deactivated_after_creation_does_not_realert(self):
        self.add_watch()
        first = self.process()
        self.assertIsNotNone(first)
        self.watchlist.deactivate_watchlist_entry("GJ01AB1234")
        second = self.process(timestamp=_ts(120))
        self.assertIsNone(second)

    # real plate_read linkage (FK to plate_reads)
    def test_plate_read_id_stored(self):
        self.add_watch()
        read_id = self.plates.insert_plate_read(
            PlateRead(
                canonical_vehicle_id=123,
                camera_id="cam01",
                raw_ocr="GJ01AB1234",
                normalized_plate="GJ01AB1234",
                timestamp=T0,
            )
        )
        alert = self.process(plate_read_id=read_id)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.plate_read_id, read_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)


