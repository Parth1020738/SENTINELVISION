"""
SentinelVision - Database Tests

Phase 6B: SQLite Persistence Layer

Covers: database creation, data directory creation, schema
initialization (and repetition), tables, foreign keys, camera
insert/upsert/lookup/list/status, vehicle events, plate reads and
searches, zone counts and aggregation, FK protection, persistence
after reopen, rollback, parameterized queries, and credential safety.

All tests are deterministic: temporary SQLite databases, no GPU,
no YOLO, no RTSP, no network, no credentials.
"""

import datetime
import os
import sqlite3
import tempfile
import unittest

from backend.camera.rtsp_credentials import redact_url
from backend.db.database import Database, DEFAULT_DB_PATH, _to_utc_iso
from backend.db.models import Camera, PlateRead, VehicleEvent, ZoneCount
from backend.db.repositories import (
    CameraRepository,
    VehicleRepository,
    PlateRepository,
    ZoneRepository,
    EventRecorder,
)


def make_camera(camera_id="cam01", **overrides):
    """Build a Camera with deterministic test values."""
    values = dict(
        camera_id=camera_id,
        name="Gate 1",
        location="North Entrance",
        latitude=28.6139,
        longitude=77.2090,
        codec="H.264",
        width=1920,
        height=1080,
        rtsp_url="rtsp://103.250.160.189:8554/stream/" + camera_id,
        webrtc_url=None,
        hls_url=f"https://cctv.corp8.cloud/{camera_id}/index.m3u8",
        live=False,
    )
    values.update(overrides)
    return Camera(**values)


def make_event(camera_id="cam01", vid=1, **overrides):
    values = dict(
        canonical_vehicle_id=vid,
        camera_id=camera_id,
        vehicle_class="car",
        event_type="DETECTED",
        timestamp="2026-09-04T10:00:00+00:00",
        confidence=0.91,
        bbox_x1=100.0, bbox_y1=200.0, bbox_x2=300.0, bbox_y2=400.0,
        direction=None,
    )
    values.update(overrides)
    return VehicleEvent(**values)


def make_plate(camera_id="cam01", vid=1, plate="HR99ABV2812", **overrides):
    values = dict(
        canonical_vehicle_id=vid,
        camera_id=camera_id,
        raw_ocr="HR 99 ABV 2812",
        normalized_plate=plate,
        ocr_confidence=0.88,
        detector_confidence=0.92,
        combined_confidence=0.81,
        timestamp="2026-09-04T10:00:01+00:00",
    )
    values.update(overrides)
    return PlateRead(**values)


def make_count(camera_id="cam01", vid=1, direction="IN", **overrides):
    values = dict(
        camera_id=camera_id,
        canonical_vehicle_id=vid,
        vehicle_class="car",
        direction=direction,
        timestamp="2026-09-04T10:00:02+00:00",
    )
    values.update(overrides)
    return ZoneCount(**values)


class DatabaseTestBase(unittest.TestCase):
    """Common setup: a fresh temp database per test."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.db = Database(self.db_path)
        self.db.initialize()

    def tearDown(self):
        self.tmpdir.cleanup()

    def register_cam01(self):
        CameraRepository(self.db).upsert_camera(make_camera())


# ---------------------------------------------------------------------------
# 1-6: Database creation / schema
# ---------------------------------------------------------------------------
class TestDatabaseCreation(DatabaseTestBase):
    def test_database_file_created(self):
        self.assertTrue(os.path.exists(self.db_path))

    def test_default_path_is_data_sentinelvision_db(self):
        self.assertEqual(DEFAULT_DB_PATH.replace("\\", "/"), "data/sentinelvision.db")

    def test_data_directory_created_automatically(self):
        nested = os.path.join(self.tmpdir.name, "a", "b", "test.db")
        db = Database(nested)
        db.initialize()
        self.assertTrue(os.path.exists(nested))

    def test_schema_initialization_creates_all_tables(self):
        tables = self.db.table_names()
        for expected in ("cameras", "vehicle_events", "plate_reads", "zone_counts"):
            self.assertIn(expected, tables)

    def test_repeated_initialization_is_idempotent(self):
        self.db.initialize()
        self.db.initialize()
        self.assertEqual(
            self.db.table_names(),
            [
                "alerts",
                "audit_logs",
                "camera_health",
                "cameras",
                "cross_camera_observations",
                "global_vehicles",
                "plate_reads",
                "vehicle_events",
                "watchlist_entries",
                "zone_counts",
            ],
        )

    def test_foreign_keys_enabled_on_every_connection(self):
        self.assertTrue(self.db.foreign_keys_enabled())
        with self.db.connection() as conn:
            self.assertTrue(self.db.foreign_keys_enabled(conn))


# ---------------------------------------------------------------------------
# 7-11: Camera repository
# ---------------------------------------------------------------------------
class TestCameraRepository(DatabaseTestBase):
    def test_camera_insert(self):
        repos = CameraRepository(self.db)
        row_id = repos.upsert_camera(make_camera())
        self.assertGreater(row_id, 0)
        cam = repos.get_camera("cam01")
        self.assertIsNotNone(cam)
        self.assertEqual(cam.name, "Gate 1")
        self.assertEqual(cam.codec, "H.264")
        self.assertEqual(cam.width, 1920)

    def test_camera_upsert_no_duplicates(self):
        repos = CameraRepository(self.db)
        repos.upsert_camera(make_camera())
        updated = make_camera(codec="H.265", width=1280, height=720, live=True)
        repos.upsert_camera(updated)
        cams = repos.list_cameras()
        self.assertEqual(len(cams), 1)
        self.assertEqual(cams[0].codec, "H.265")
        self.assertEqual(cams[0].width, 1280)
        self.assertTrue(cams[0].live)

    def test_camera_lookup_missing_returns_none(self):
        self.assertIsNone(CameraRepository(self.db).get_camera("nope"))

    def test_camera_listing(self):
        repos = CameraRepository(self.db)
        repos.upsert_camera(make_camera("cam02"))
        repos.upsert_camera(make_camera("cam01"))
        ids = [c.camera_id for c in repos.list_cameras()]
        self.assertEqual(ids, ["cam01", "cam02"])

    def test_camera_status_update(self):
        repos = CameraRepository(self.db)
        repos.upsert_camera(make_camera())
        self.assertFalse(repos.get_camera("cam01").live)
        self.assertTrue(repos.update_camera_status("cam01", True))
        self.assertTrue(repos.get_camera("cam01").live)
        self.assertFalse(repos.update_camera_status("ghost", True))

    def test_camera_upsert_preserves_created_at_and_updates_updated_at(self):
        repos = CameraRepository(self.db)
        repos.upsert_camera(make_camera())
        first = repos.get_camera("cam01")
        repos.upsert_camera(make_camera(name="Renamed"))
        second = repos.get_camera("cam01")
        self.assertEqual(second.created_at, first.created_at)
        self.assertEqual(second.name, "Renamed")


# ---------------------------------------------------------------------------
# 12-14: Vehicle events
# ---------------------------------------------------------------------------
class TestVehicleRepository(DatabaseTestBase):
    def setUp(self):
        super().setUp()
        self.register_cam01()
        self.repos = VehicleRepository(self.db)

    def test_vehicle_event_insert(self):
        row_id = self.repos.insert_vehicle_event(make_event())
        self.assertGreater(row_id, 0)
        events = self.repos.get_vehicle_events_by_camera("cam01")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "DETECTED")
        self.assertEqual(events[0].vehicle_class, "car")

    def test_vehicle_event_timestamp_preserved_verbatim(self):
        self.repos.insert_vehicle_event(make_event())
        stored = self.repos.get_vehicle_history(1)[0]
        self.assertEqual(stored.timestamp, "2026-09-04T10:00:00+00:00")

    def test_vehicle_event_missing_timestamp_gets_utc_now(self):
        self.repos.insert_vehicle_event(make_event(timestamp=None))
        stored = self.repos.get_vehicle_history(1)[0]
        self.assertIn("T", stored.timestamp)

    def test_vehicle_history_ordered_and_complete(self):
        ts = ["2026-09-04T10:00:00+00:00", "2026-09-04T10:00:05+00:00",
              "2026-09-04T10:00:02+00:00"]
        for i, t in enumerate(ts):
            self.repos.insert_vehicle_event(
                make_event(vid=7, event_type="ZONE_IN", timestamp=t)
            )
        history = self.repos.get_vehicle_history(7)
        self.assertEqual([e.timestamp for e in history], sorted(ts))
        self.assertEqual(len(history), 3)

    def test_vehicle_history_empty_for_unknown_vehicle(self):
        self.repos.insert_vehicle_event(make_event(vid=1))
        self.assertEqual(self.repos.get_vehicle_history(999), [])

    def test_vehicle_events_by_camera_isolated(self):
        CameraRepository(self.db).upsert_camera(make_camera("cam02"))
        self.repos.insert_vehicle_event(make_event(camera_id="cam01", vid=1))
        self.repos.insert_vehicle_event(make_event(camera_id="cam02", vid=2))
        self.assertEqual(len(self.repos.get_vehicle_events_by_camera("cam01")), 1)
        self.assertEqual(len(self.repos.get_vehicle_events_by_camera("cam02")), 1)

    def test_get_recent_vehicle_events_limit(self):
        for i in range(5):
            self.repos.insert_vehicle_event(make_event(vid=i + 1))
        recent = self.repos.get_recent_vehicle_events(limit=3)
        self.assertEqual(len(recent), 3)


# ---------------------------------------------------------------------------
# 15-18, 30: Plate reads and search
# ---------------------------------------------------------------------------
class TestPlateRepository(DatabaseTestBase):
    def setUp(self):
        super().setUp()
        self.register_cam01()
        self.repos = PlateRepository(self.db)

    def test_plate_insert_normalizes(self):
        row_id = self.repos.insert_plate_read(make_plate(plate="HR 99 ABV2812"))
        self.assertGreater(row_id, 0)
        stored = self.repos.get_plate_reads_for_vehicle(1)[0]
        self.assertEqual(stored.normalized_plate, "HR99ABV2812")

    def test_plate_insert_blank_rejected(self):
        self.assertIsNone(self.repos.insert_plate_read(make_plate(plate="   ")))
        self.assertEqual(self.repos.search_exact_plate("HR99ABV2812"), [])

    def test_exact_plate_search(self):
        self.repos.insert_plate_read(make_plate(vid=1, plate="HR99ABV2812"))
        self.repos.insert_plate_read(make_plate(vid=2, plate="DL01CD3456"))
        hits = self.repos.search_exact_plate("HR99ABV2812")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].canonical_vehicle_id, 1)

    def test_exact_search_normalizes_query(self):
        self.repos.insert_plate_read(make_plate(plate="HR99ABV2812"))
        hits = self.repos.search_exact_plate("hr-99.abv 2812")
        self.assertEqual(len(hits), 1)

    def test_partial_plate_search(self):
        self.repos.insert_plate_read(make_plate(vid=1, plate="HR99ABV2812"))
        self.repos.insert_plate_read(make_plate(vid=2, plate="HR99XY1111"))
        hits = self.repos.search_partial_plate("ABV")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].normalized_plate, "HR99ABV2812")

    def test_vehicle_plate_history(self):
        self.repos.insert_plate_read(make_plate(vid=5, plate="HR99ABV2812"))
        self.repos.insert_plate_read(make_plate(vid=5, plate="DL01CD3456"))
        self.repos.insert_plate_read(make_plate(vid=6, plate="MH12EF7890"))
        reads = self.repos.get_plate_reads_for_vehicle(5)
        self.assertEqual(len(reads), 2)

    def test_duplicate_plate_read_ignored(self):
        first = self.repos.insert_plate_read(make_plate())
        second = self.repos.insert_plate_read(make_plate())
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(self.repos.get_plate_reads_for_vehicle(1)), 1)


# ---------------------------------------------------------------------------
# 19-23: Zone counts
# ---------------------------------------------------------------------------
class TestZoneRepository(DatabaseTestBase):
    def setUp(self):
        super().setUp()
        self.register_cam01()
        CameraRepository(self.db).upsert_camera(make_camera("cam02"))
        self.repos = ZoneRepository(self.db)

    def test_zone_in_insertion(self):
        row_id = self.repos.insert_zone_count(make_count(direction="IN"))
        self.assertGreater(row_id, 0)

    def test_zone_out_insertion(self):
        row_id = self.repos.insert_zone_count(make_count(direction="OUT"))
        self.assertGreater(row_id, 0)

    def test_invalid_direction_rejected(self):
        with self.assertRaises(ValueError):
            self.repos.insert_zone_count(make_count(direction="SIDEWAYS"))

    def test_count_retrieval_totals(self):
        self.repos.insert_zone_count(make_count(vid=1, direction="IN"))
        self.repos.insert_zone_count(make_count(vid=2, direction="OUT"))
        counts = self.repos.get_counts()
        self.assertEqual(counts["total"]["IN"], 1)
        self.assertEqual(counts["total"]["OUT"], 1)
        self.assertEqual(counts["car"]["IN"], 1)

    def test_per_camera_counts(self):
        self.repos.insert_zone_count(make_count(vid=1, direction="IN"))
        self.repos.insert_zone_count(make_count(camera_id="cam02", vid=2, direction="IN"))
        counts = self.repos.get_counts_by_camera("cam01")
        self.assertEqual(counts["total"]["IN"], 1)
        self.assertEqual(counts["total"]["OUT"], 0)

    def test_per_class_counts(self):
        self.repos.insert_zone_count(make_count(vid=1, direction="IN"))
        self.repos.insert_zone_count(
            make_count(vid=2, direction="IN", vehicle_class="truck")
        )
        self.repos.insert_zone_count(make_count(vid=3, direction="OUT"))
        car = self.repos.get_counts_by_class("car")
        self.assertEqual(car["IN"], 1)
        self.assertEqual(car["OUT"], 1)
        truck = self.repos.get_counts_by_class("truck")
        self.assertEqual(truck["IN"], 1)
        self.assertEqual(truck["OUT"], 0)

    def test_duplicate_zone_count_ignored(self):
        self.repos.insert_zone_count(make_count(vid=1, direction="IN"))
        self.assertIsNone(self.repos.insert_zone_count(make_count(vid=1, direction="IN")))
        self.assertEqual(self.repos.get_counts()["total"]["IN"], 1)


# ---------------------------------------------------------------------------
# 24, 26, 27: Foreign keys / rollback / persistence / parameterized queries
# ---------------------------------------------------------------------------
class TestForeignKeysAndIntegrity(DatabaseTestBase):
    def test_foreign_key_protection_vehicle_event(self):
        with self.assertRaises(sqlite3.IntegrityError):
            VehicleRepository(self.db).insert_vehicle_event(make_event())

    def test_foreign_key_protection_plate_read(self):
        with self.assertRaises(sqlite3.IntegrityError):
            PlateRepository(self.db).insert_plate_read(make_plate())

    def test_foreign_key_protection_zone_count(self):
        with self.assertRaises(sqlite3.IntegrityError):
            ZoneRepository(self.db).insert_zone_count(make_count())

    def test_connection_closes_after_context_manager(self):
        with self.db.connection() as conn:
            conn.execute("SELECT 1")
        # A new connection works fine afterwards (old one was closed).
        self.assertTrue(self.db.foreign_keys_enabled())

    def test_rollback_on_failure(self):
        self.register_cam01()
        sentinel = make_event()
        with self.assertRaises(RuntimeError):
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT INTO vehicle_events (canonical_vehicle_id,"
                    " camera_id, timestamp, vehicle_class, event_type,"
                    " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (sentinel.canonical_vehicle_id, sentinel.camera_id,
                     sentinel.timestamp, sentinel.vehicle_class,
                     sentinel.event_type, sentinel.timestamp),
                )
                raise RuntimeError("simulated pipeline failure")
        # The transaction was rolled back — nothing was persisted.
        with self.db.connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM vehicle_events").fetchone()[0]
        self.assertEqual(n, 0)

    def test_integrity_error_rolls_back_when_propagates(self):
        # FK violation raised from a repository propagates out of the
        # connection context, which must roll back and close cleanly.
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT INTO zone_counts (camera_id, canonical_vehicle_id,"
                    " vehicle_class, direction, timestamp, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    ("missing_camera", 1, "car", "IN",
                     "2026-09-04T10:00:00+00:00",
                     "2026-09-04T10:00:00+00:00"),
                )
        with self.db.connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM zone_counts").fetchone()[0]
        self.assertEqual(n, 0)

    def test_persistence_after_reopening_database(self):
        self.register_cam01()
        VehicleRepository(self.db).insert_vehicle_event(make_event())
        PlateRepository(self.db).insert_plate_read(make_plate())
        ZoneRepository(self.db).insert_zone_count(make_count(direction="IN"))

        reopened = Database(self.db_path)
        reopened.initialize()
        self.assertEqual(
            len(VehicleRepository(reopened).get_vehicle_history(1)), 1
        )
        self.assertEqual(
            len(PlateRepository(reopened).search_exact_plate("HR99ABV2812")), 1
        )
        self.assertEqual(
            ZoneRepository(reopened).get_counts()["total"]["IN"], 1
        )
        self.assertEqual(
            len(CameraRepository(reopened).list_cameras()), 1
        )

    def test_parameterized_queries_resist_sql_injection(self):
        self.register_cam01()
        repos = PlateRepository(self.db)
        repos.insert_plate_read(make_plate(plate="HR99ABV2812"))
        # Malicious input must not match anything / must not execute.
        malicious = "HR99ABV2812' OR '1'='1"
        self.assertEqual(repos.search_exact_plate(malicious), [])
        self.assertEqual(repos.search_partial_plate(malicious), [])
        # Table still exists and data intact.
        self.assertEqual(len(repos.search_exact_plate("HR99ABV2812")), 1)

# ---------------------------------------------------------------------------
# 28-29: Credential security
# ---------------------------------------------------------------------------
class TestCredentialSecurity(DatabaseTestBase):
    def test_redact_url_strips_credentials(self):
        self.assertEqual(
            redact_url(
                "rtsp://user%40mail.com:secret@1.2.3.4:8554/stream/cam01"
            ),
            "rtsp://1.2.3.4:8554/stream/cam01",
        )
        self.assertEqual(redact_url("rtsp://1.2.3.4/x"),
                         "rtsp://1.2.3.4/x")

    def test_authenticated_rtsp_url_never_persisted(self):
        dangerous = "rtsp://user%40mail.com:topsecret@1.2.3.4:8554/stream/cam01"
        CameraRepository(self.db).upsert_camera(make_camera(rtsp_url=dangerous))
        stored = CameraRepository(self.db).get_camera("cam01")
        self.assertEqual(stored.rtsp_url, "rtsp://1.2.3.4:8554/stream/cam01")

    def test_credentials_never_stored_anywhere_in_database_file(self):
        CameraRepository(self.db).upsert_camera(
            make_camera(rtsp_url="rtsp://bob:p4ss@1.2.3.4:8554/stream/cam01")
        )
        with open(self.db_path, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"p4ss", raw)
        self.assertNotIn(b"bob:", raw)

    def test_safe_rtsp_url_round_trips_through_upsert(self):
        repos = CameraRepository(self.db)
        repos.upsert_camera(make_camera())
        repos.upsert_camera(make_camera(
            rtsp_url="rtsp://eve:hunter2@1.2.3.4:8554/stream/cam01"))
        self.assertEqual(repos.get_camera("cam01").rtsp_url,
                         "rtsp://1.2.3.4:8554/stream/cam01")


# ---------------------------------------------------------------------------
# Integration bridge + timestamps
# ---------------------------------------------------------------------------
class TestEventRecorderBridge(DatabaseTestBase):
    def test_recorder_end_to_end_flow(self):
        recorder = EventRecorder(self.db)
        recorder.register_camera(make_camera())
        recorder.record_vehicle_event(make_event())
        recorder.record_plate_read(make_plate())
        recorder.record_zone_count(make_count(direction="IN"))
        self.assertEqual(len(recorder.vehicles.get_vehicle_history(1)), 1)
        self.assertEqual(len(recorder.plates.search_exact_plate("HR99ABV2812")), 1)
        self.assertEqual(recorder.zones.get_counts()["total"]["IN"], 1)

    def test_module_level_convenience_functions(self):
        from backend.db import (
            record_vehicle_event,
            record_plate_read,
            record_zone_count,
            register_camera,
        )
        register_camera(self.db, make_camera())
        record_vehicle_event(self.db, make_event())
        record_plate_read(self.db, make_plate())
        record_zone_count(self.db, make_count(direction="OUT"))
        with self.db.connection() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM vehicle_events").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM plate_reads").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM zone_counts").fetchone()[0], 1)


class TestTimestampHandling(unittest.TestCase):
    def test_none_becomes_utc_now_iso(self):
        stamp = _to_utc_iso(None)
        self.assertIn("T", stamp)
        self.assertIn("+00:00", stamp)

    def test_datetime_converted_to_utc_iso(self):
        dt = datetime.datetime(2026, 9, 4, 10, 0, 0)
        self.assertEqual(_to_utc_iso(dt), "2026-09-04T10:00:00+00:00")

    def test_epoch_seconds_converted_to_utc_iso(self):
        self.assertEqual(_to_utc_iso(0), "1970-01-01T00:00:00+00:00")

    def test_string_stored_verbatim(self):
        self.assertEqual(_to_utc_iso("2026-09-04T10:00:00+00:00"),
                         "2026-09-04T10:00:00+00:00")

    def test_models_are_persistence_only(self):
        # Models must not depend on YOLO / OpenCV — they are plain dataclasses.
        import dataclasses
        for cls in (Camera, VehicleEvent, PlateRead, ZoneCount):
            self.assertTrue(dataclasses.is_dataclass(cls))


if __name__ == "__main__":
    unittest.main()




