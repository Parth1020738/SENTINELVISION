"""
SentinelVision - Watchlist Repository Tests

Phase 7: deterministic tests for the watchlist repository on a
temporary SQLite database.  No GPU / RTSP / internet / YOLO / real
credentials.

Run:  python -m backend.db.test_watchlist -v
"""

import os
import tempfile
import unittest

from backend.db.database import Database
from backend.db.models import WatchlistEntry
from backend.db.repositories import WatchlistRepository


class WatchlistTestCase(unittest.TestCase):
    """Shared fixture: temp database + initialized schema."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._tmpdir.name, "test.db"))
        self.db.initialize()
        self.repo = WatchlistRepository(self.db)

    def tearDown(self):
        self._tmpdir.cleanup()

    def add_entry(self, plate="GJ01AB1234", **kwargs):
        entry = WatchlistEntry(
            normalized_plate=plate,
            reason=kwargs.get("reason", "Reported stolen vehicle"),
            category=kwargs.get("category", "STOLEN"),
            priority=kwargs.get("priority", "HIGH"),
            notes=kwargs.get("notes", "Optional note"),
            active=kwargs.get("active", True),
        )
        entry.id = self.repo.add_watchlist_entry(entry)
        return entry


class TestWatchlistRepository(WatchlistTestCase):
    # 1. add plate
    def test_add_plate(self):
        entry = self.add_entry()
        self.assertIsNotNone(entry.id)
        self.assertEqual(entry.normalized_plate, "GJ01AB1234")

    # 2. normalize plate on storage
    def test_normalize_plate_on_storage(self):
        entry = WatchlistEntry(
            normalized_plate="GJ 01 AB 1234",
            reason="Reported stolen vehicle",
            category="STOLEN",
            priority="HIGH",
        )
        entry_id = self.repo.add_watchlist_entry(entry)
        stored = self.repo.get_watchlist_entry(entry_id)
        self.assertEqual(stored.normalized_plate, "GJ01AB1234")

    # 3. duplicate normalized plate rejected
    def test_duplicate_normalized_plate_rejected(self):
        self.add_entry("GJ01AB1234")
        duplicate = WatchlistEntry(
            normalized_plate="GJ 01 AB 1234",  # same normalized plate
            reason="Duplicate attempt",
        )
        with self.assertRaises(ValueError):
            self.repo.add_watchlist_entry(duplicate)

    # 4. lookup by plate (raw and normalized forms)
    def test_lookup_by_plate(self):
        self.add_entry("GJ01AB1234")
        by_normalized = self.repo.get_watchlist_entry_by_plate("GJ01AB1234")
        by_raw = self.repo.get_watchlist_entry_by_plate("GJ 01-ab-1234")
        self.assertIsNotNone(by_normalized)
        self.assertIsNotNone(by_raw)
        self.assertEqual(by_normalized.id, by_raw.id)

    def test_lookup_unknown_plate_returns_none(self):
        self.assertIsNone(self.repo.get_watchlist_entry_by_plate("ZZ00ZZ0000"))

    # 6. active filter
    def test_active_filter(self):
        self.add_entry("GJ01AB1234")
        self.add_entry("MH12CD3456")
        self.repo.deactivate_watchlist_entry("GJ01AB1234")
        active = self.repo.list_watchlist_entries(active=True)
        inactive = self.repo.list_watchlist_entries(active=False)
        self.assertEqual([e.normalized_plate for e in active], ["MH12CD3456"])
        self.assertEqual([e.normalized_plate for e in inactive], ["GJ01AB1234"])

    # 7. category filter
    def test_category_filter(self):
        self.add_entry("GJ01AB1234", category="STOLEN")
        self.add_entry("MH12CD3456", category="WANTED")
        stolen = self.repo.list_watchlist_entries(category="STOLEN")
        self.assertEqual(len(stolen), 1)
        self.assertEqual(stolen[0].normalized_plate, "GJ01AB1234")

    # 8. priority filter
    def test_priority_filter(self):
        self.add_entry("GJ01AB1234", priority="HIGH")
        self.add_entry("MH12CD3456", priority="LOW")
        high = self.repo.list_watchlist_entries(priority="HIGH")
        self.assertEqual(len(high), 1)
        self.assertEqual(high[0].normalized_plate, "GJ01AB1234")

    # 9. update
    def test_update(self):
        self.add_entry("GJ01AB1234")
        ok = self.repo.update_watchlist_entry(
            "GJ01AB1234", priority="CRITICAL", notes="Escalated"
        )
        self.assertTrue(ok)
        entry = self.repo.get_watchlist_entry_by_plate("GJ01AB1234")
        self.assertEqual(entry.priority, "CRITICAL")
        self.assertEqual(entry.notes, "Escalated")

    def test_update_invalid_category_rejected(self):
        self.add_entry("GJ01AB1234")
        with self.assertRaises(ValueError):
            self.repo.update_watchlist_entry("GJ01AB1234", category="NOPE")

    # 10. deactivate (soft disable)
    def test_deactivate(self):
        self.add_entry("GJ01AB1234")
        ok = self.repo.deactivate_watchlist_entry("GJ01AB1234")
        self.assertTrue(ok)
        entry = self.repo.get_watchlist_entry_by_plate("GJ01AB1234")
        self.assertFalse(entry.active)
        # Row still exists — soft disable, not deletion.
        self.assertIsNotNone(self.repo.get_watchlist_entry(entry.id))

    def test_deactivate_unknown_plate_returns_false(self):
        self.assertFalse(self.repo.deactivate_watchlist_entry("ZZ00ZZ0000"))

    # 11. inactive plate excluded from active lookups by the engine
    def test_inactive_plate_not_matched_as_active(self):
        self.add_entry("GJ01AB1234")
        self.repo.deactivate_watchlist_entry("GJ01AB1234")
        entry = self.repo.get_watchlist_entry_by_plate("GJ01AB1234")
        self.assertIsNotNone(entry)
        self.assertFalse(entry.active)

    # validation extras
    def test_empty_plate_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.add_watchlist_entry(
                WatchlistEntry(normalized_plate="  --  ", reason="x")
            )

    def test_invalid_category_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.add_watchlist_entry(
                WatchlistEntry(
                    normalized_plate="GJ01AB1234", reason="x", category="NOPE"
                )
            )

    def test_invalid_priority_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.add_watchlist_entry(
                WatchlistEntry(
                    normalized_plate="GJ01AB1234", reason="x", priority="URGENT"
                )
            )


class TestMigrationSafety(WatchlistTestCase):
    """Phase 7 tables must be additive — existing data stays valid."""

    def test_phase6_data_survives_reinitialization(self):
        from backend.db.models import Camera
        from backend.db.repositories import CameraRepository

        cameras = CameraRepository(self.db)
        cameras.upsert_camera(Camera(camera_id="cam01", name="Gate 1"))
        self.db.initialize()
        self.db.initialize()
        self.assertIsNotNone(cameras.get_camera("cam01"))
        self.assertIn("watchlist_entries", self.db.table_names())
        self.assertIn("alerts", self.db.table_names())


if __name__ == "__main__":
    unittest.main(verbosity=2)

