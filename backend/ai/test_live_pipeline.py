"""
SentinelVision - Live Pipeline Tests (Phase 8)

Offline, deterministic tests for ``backend.ai.live_pipeline.LivePipeline``.

Run:  python -m backend.ai.test_live_pipeline -v

All heavy/real components (CameraStream, YOLO tracker, ANPR, repositories)
are replaced with Fakes so no GPU, camera, internet, or real credentials are
required.  The pure Phase 2/3/4 algorithms (class stabiliser, continuity
manager, zone counter) and the Phase 6B/7 repository + alert layers run for
real against a temporary SQLite database.

The most important invariant checked here:
    Given a fake frame PTS and fake vehicle/plate results, the *exact* PTS-
    derived timestamp propagates to vehicle_events, zone_counts,
    plate_reads, and alerts.  No event may be replaced with datetime.now().
"""

import os
import tempfile
import unittest

from backend.ai.anpr_engine import ANPRResult, VehicleInfo
from backend.ai.live_pipeline import LivePipeline
from backend.ai.track_continuity_manager import TrackContinuityManager
from backend.ai.vehicle_class_stabilizer import VehicleClassStabilizer
from backend.ai.vehicle_tracker import VehicleObservation
from backend.ai.zone_counter import ZoneCounter
from backend.db.database import Database, _to_utc_iso
from backend.db.models import Camera, WatchlistEntry
from backend.db.repositories import EventRecorder, WatchlistRepository
from backend.services.alert_engine import AlertEngine

# ---------------------------------------------------------------------------
# Fakes (no real camera / models / network)
# ---------------------------------------------------------------------------
class FakeStream:
    """Stand-in for CameraStream: yields a planned sequence of (ok, frame, pts)."""

    def __init__(self, frames, resolution=(1920, 1080)):
        self._frames = list(frames)
        self.resolution = tuple(resolution)
        self.released = False
        self.connected = False

    def connect(self):
        self.connected = True
        return True

    def read(self):
        if self._frames:
            item = self._frames.pop(0)
        else:
            item = (False, None, None)
        return item

    def release(self):
        self.released = True


class FakeTracker:
    """Stand-in for VehicleTracker.

    ``returns`` may be a list-of-lists (one list per call) or a callable
    ``callable(frame, frame_number) -> list[VehicleObservation]``.
    """

    def __init__(self, returns=None):
        self.returns = returns if returns is not None else []
        self._i = 0
        self.calls = []

    def track(self, frame, frame_number):
        self.calls.append(frame_number)
        if callable(self.returns):
            return list(self.returns(frame, frame_number))
        if not self.returns:
            return []
        if self._i < len(self.returns):
            obs = list(self.returns[self._i])
            self._i += 1
        else:
            obs = list(self.returns[-1])  # reuse last frame
        return obs

    def get_device_info(self):
        return {"gpu_name": "FAKE-GPU", "cuda_available": False}


class FakeANPR:
    """Stand-in for ANPREngine.

    Returns ``result`` only on the configured frame numbers, capturing the
    exact timestamp it was handed.
    """

    def __init__(self, result=None, on_frames=()):
        self.result = result
        self.on_frames = set(on_frames)
        self.calls = []  # (frame_number, timestamp, [(canonical_id, bbox), ...])

    def process_frame(self, frame, vehicles, frame_number=0, timestamp=None):
        seen = [(v.canonical_id, tuple(v.bbox)) for v in vehicles]
        self.calls.append((frame_number, timestamp, seen))
        if self.result is None or frame_number not in self.on_frames:
            return []
        r = self.result
        return [
            ANPRResult(
                canonical_vehicle_id=r.canonical_vehicle_id,
                vehicle_class=r.vehicle_class,
                plate_text=r.plate_text,
                plate_detection_confidence=r.plate_detection_confidence,
                ocr_confidence=r.ocr_confidence,
                combined_confidence=r.combined_confidence,
                frame_number=frame_number,
                timestamp=timestamp,
                bbox=r.bbox,
                observation_count=(r.observation_count or 1) + 1,
            )
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
CLASS_ID = {"car": 2, "motorcycle": 3, "bus": 5, "truck": 7}


def make_vo(raw, cls, bbox, conf=0.8, frame_number=1):
    """Build a ``VehicleObservation`` from a pixel bbox."""
    x1, y1, x2, y2 = bbox
    return VehicleObservation(
        raw_track_id=raw,
        class_id=CLASS_ID[cls],
        class_name=cls,
        confidence=conf,
        bbox=(x1, y1, x2, y2),
        center=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
        frame_number=frame_number,
    )


def make_frame(w=640, h=480):
    import numpy as np

    return np.zeros((h, w, 3), dtype=np.uint8)
# ---------------------------------------------------------------------------
# Shared test fixture
# ---------------------------------------------------------------------------
ZONE_PIX = (100.0, 100.0, 500.0, 500.0)   # pixel zone for injected ZoneCounter
EPOCH0 = 1700000000.0                     # fixed wall-clock for the PTS anchor
PLATE = "HR99ABV2812"


class LivePipelineTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._tmp.name, "test.db"))
        self.db.initialize()
        self.recorder = EventRecorder(self.db)
        # FK constraints require the camera row to exist before any event.
        self.recorder.register_camera(Camera(camera_id="cam01"))
        self.watchlist = WatchlistRepository(self.db)
        self.alert_engine = AlertEngine(self.db)
        self.clock = lambda: EPOCH0  # fixed wall clock for deterministic PTS->epoch

    def tearDown(self):
        self._tmp.cleanup()

    def make_pipeline(
        self,
        *,
        tracker=None,
        anpr=None,
        stream=None,
        zone_counter=None,
        display=False,
        db_path=None,
        **kw,
    ):
        if stream is None:
            stream = FakeStream([])
        if zone_counter is None:
            zone_counter = ZoneCounter(ZONE_PIX, confirmation_frames=1)
        return LivePipeline(
            "cam01",
            db=self.db,
            db_path=db_path,
            stream=stream,
            tracker=tracker or FakeTracker(),
            stabilizer=VehicleClassStabilizer(),
            continuity=TrackContinuityManager(),
            zone_counter=zone_counter,
            anpr=anpr or FakeANPR(),
            alert_engine=self.alert_engine,
            recorder=self.recorder,
            clock=self.clock,
            display=display,
            fetch_catalogue=False,
            **kw,
        )

    # -- table query helpers ------------------------------------------------
    def _q(self, sql, args=()):
        with self.db.connection() as conn:
            return conn.execute(sql, args).fetchall()

    def vehicle_events(self):
        return self._q("SELECT * FROM vehicle_events ORDER BY id")

    def zone_counts(self):
        return self._q("SELECT * FROM zone_counts ORDER BY id")

    def plate_reads(self):
        return self._q("SELECT * FROM plate_reads ORDER BY id")

    def alerts(self):
        return self._q("SELECT * FROM alerts ORDER BY id")


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------
class TestInitialization(LivePipelineTestCase):
    def test_components_configured(self):
        pipe = self.make_pipeline()
        self.assertEqual(pipe.camera_id, "cam01")
        self.assertTrue(pipe.db is self.db)
        self.assertTrue(pipe.recorder is self.recorder)
        self.assertTrue(pipe.alert_engine is self.alert_engine)
        self.assertIsInstance(pipe.stabilizer, VehicleClassStabilizer)
        self.assertIsInstance(pipe.continuity, TrackContinuityManager)
        self.assertIsInstance(pipe.zone_counter, ZoneCounter)
        s = pipe.get_stats()
        self.assertEqual(s["frames"], 0)
        self.assertEqual(s["detections"], 0)
        self.assertEqual(s["alerts"], 0)

    def test_zone_scaled_from_normalized_when_not_injected(self):
        pipe = LivePipeline(
            "cam01",
            db=self.db,
            clock=self.clock,
            tracker=FakeTracker(),
            stabilizer=VehicleClassStabilizer(),
            continuity=TrackContinuityManager(),
            anpr=FakeANPR(),
            stream=FakeStream([], resolution=(1000, 800)),
            alert_engine=self.alert_engine,
            recorder=self.recorder,
            zone=(0.10, 0.50, 0.90, 0.80),
            fetch_catalogue=False,
        )
        pipe._ensure_zone((1000, 800))
        self.assertEqual(pipe._pixel_zone, (100.0, 400.0, 900.0, 640.0))
# ---------------------------------------------------------------------------
# 2. Frame processing
# ---------------------------------------------------------------------------
class TestFrameProcessing(LivePipelineTestCase):
    def test_counts_and_canonical_returned(self):
        def scenario(frame, fn):
            return [make_vo(7, "car", (200, 200, 300, 400), frame_number=fn)]

        pipe = self.make_pipeline(
            tracker=FakeTracker(returns=scenario),
            anpr=FakeANPR(),
        )
        canonical = pipe.process_frame(make_frame(), pts_ms=1000.0)
        self.assertEqual(pipe.frames_processed, 1)
        self.assertEqual(pipe.detections, 1)
        self.assertEqual(pipe.get_stats()["raw_tracks"], 1)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(canonical[0].bytetrack_id, 7)  # raw id from tracker

    def test_empty_frame_no_crash(self):
        pipe = self.make_pipeline(tracker=FakeTracker(returns=[]))
        pipe.process_frame(make_frame(), pts_ms=500.0)
        self.assertEqual(pipe.frames_processed, 1)
        self.assertEqual(pipe.detections, 0)


# ---------------------------------------------------------------------------
# 3. Canonical vehicle ID usage (never raw ByteTrack ID)
# ---------------------------------------------------------------------------
class TestCanonicalIdUsage(LivePipelineTestCase):
    def test_events_use_canonical_id_not_raw(self):
        def scenario(frame, fn):
            return [make_vo(42, "car", (50, 50, 80, 80), frame_number=fn)]

        pipe = self.make_pipeline(tracker=FakeTracker(returns=scenario))
        pipe.process_frame(make_frame(), pts_ms=0.0)
        events = self.vehicle_events()
        # canonical starts at 100, NOT the raw id 42.
        self.assertEqual(events[0]["canonical_vehicle_id"], 100)
        self.assertNotEqual(events[0]["canonical_vehicle_id"], 42)


# ---------------------------------------------------------------------------
# 4. Zone event persistence
# ---------------------------------------------------------------------------
class TestZoneEventPersistence(LivePipelineTestCase):
    def test_zone_in_recorded(self):
        # frame1: outside; frame2: inside -> confirmed IN (confirmation_frames=1)
        def scenario(frame, fn):
            if fn == 1:
                return [make_vo(1, "car", (20, 20, 40, 40), frame_number=fn)]  # outside
            return [make_vo(1, "car", (300, 300, 320, 320), frame_number=fn)]  # inside

        pipe = self.make_pipeline(tracker=FakeTracker(returns=scenario))
        pipe.process_frame(make_frame(), pts_ms=0.0)
        pipe.process_frame(make_frame(), pts_ms=1000.0)

        zc = self.zone_counts()
        self.assertEqual(len(zc), 1)
        self.assertEqual(zc[0]["direction"], "IN")
        self.assertEqual(zc[0]["canonical_vehicle_id"], 100)
        self.assertEqual(zc[0]["camera_id"], "cam01")
        self.assertEqual(pipe.zone_in, 1)

        ve = self.vehicle_events()
        types = {r["event_type"] for r in ve}
        self.assertIn("ZONE_IN", types)
# ---------------------------------------------------------------------------
# 5. Plate read persistence
# ---------------------------------------------------------------------------
class TestPlateReadPersistence(LivePipelineTestCase):
    def test_plate_read_fields(self):
        result = ANPRResult(
            canonical_vehicle_id=100,
            vehicle_class="car",
            plate_text=PLATE,
            plate_detection_confidence=0.82,
            ocr_confidence=0.91,
            combined_confidence=0.7462,
            bbox=(200, 200, 300, 220),
        )

        def scenario(frame, fn):
            return [make_vo(1, "car", (200, 200, 300, 400), frame_number=fn)]

        pipe = self.make_pipeline(
            tracker=FakeTracker(returns=scenario),
            anpr=FakeANPR(result=result, on_frames={1}),
        )
        pipe.process_frame(make_frame(), pts_ms=0.0)
        rows = self.plate_reads()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["canonical_vehicle_id"], 100)
        self.assertEqual(r["camera_id"], "cam01")
        self.assertEqual(r["normalized_plate"], PLATE)
        self.assertEqual(r["raw_ocr"], PLATE)
        self.assertAlmostEqual(r["ocr_confidence"], 0.91)
        self.assertAlmostEqual(r["detector_confidence"], 0.82)
        self.assertAlmostEqual(r["combined_confidence"], 0.7462)


# ---------------------------------------------------------------------------
# 6. AlertEngine invocation
# ---------------------------------------------------------------------------
class TestAlertEngineInvocation(LivePipelineTestCase):
    def test_alert_created_for_watchlist_plate(self):
        self.watchlist.add_watchlist_entry(
            WatchlistEntry(
                normalized_plate=PLATE,
                reason="Reported stolen",
                category="STOLEN",
                priority="HIGH",
                active=True,
            )
        )
        result = ANPRResult(
            canonical_vehicle_id=100,
            vehicle_class="car",
            plate_text=PLATE,
            plate_detection_confidence=0.8,
            ocr_confidence=0.9,
            combined_confidence=0.72,
        )

        def scenario(frame, fn):
            return [make_vo(1, "car", (200, 200, 300, 400), frame_number=fn)]

        pipe = self.make_pipeline(
            tracker=FakeTracker(returns=scenario),
            anpr=FakeANPR(result=result, on_frames={1}),
        )
        pipe.process_frame(make_frame(), pts_ms=0.0)

        rows = self.alerts()
        self.assertEqual(len(rows), 1)
        a = rows[0]
        self.assertEqual(a["normalized_plate"], PLATE)
        self.assertEqual(a["camera_id"], "cam01")
        self.assertEqual(a["canonical_vehicle_id"], 100)
        self.assertEqual(a["status"], "NEW")
        self.assertEqual(pipe.alerts, 1)


# ---------------------------------------------------------------------------
# 7. Timestamp propagation (THE critical invariant)
# ---------------------------------------------------------------------------
class TestTimestampPropagation(LivePipelineTestCase):
    def test_exact_pts_epoch_reaches_all_tables(self):
        result = ANPRResult(
            canonical_vehicle_id=100,
            vehicle_class="car",
            plate_text=PLATE,
            plate_detection_confidence=0.8,
            ocr_confidence=0.9,
            combined_confidence=0.72,
            bbox=(200, 200, 300, 220),
        )

        def scenario(frame, fn):
            if fn == 1:
                return [make_vo(1, "car", (20, 20, 40, 40), frame_number=fn)]  # outside
            return [make_vo(1, "car", (300, 300, 320, 320), frame_number=fn)]  # inside

        # ANPR returns results only on frame 2.
        pipe = self.make_pipeline(
            tracker=FakeTracker(returns=scenario),
            anpr=FakeANPR(result=result, on_frames={2}),
        )
        self.watchlist.add_watchlist_entry(
            WatchlistEntry(
                normalized_plate=PLATE,
                reason="test",
                category="SUSPICIOUS",
                priority="HIGH",
                active=True,
            )
        )

        # frame1 pts=0  -> epoch = EPOCH0
        pipe.process_frame(make_frame(), pts_ms=0.0)
        # frame2 pts=3000 -> epoch = EPOCH0 + 3.0s
        pipe.process_frame(make_frame(), pts_ms=3000.0)

        expected_first = _to_utc_iso(EPOCH0)
        expected_event = _to_utc_iso(EPOCH0 + 3.0)

        # vehicle_events: DETECTED at first epoch, ZONE_IN at event epoch.
        ve = self.vehicle_events()
        det = [r for r in ve if r["event_type"] == "DETECTED"]
        zone = [r for r in ve if r["event_type"] == "ZONE_IN"]
        self.assertEqual(det[0]["timestamp"], expected_first)
        self.assertEqual(zone[0]["timestamp"], expected_event)

        # zone_counts at event epoch.
        zc = self.zone_counts()
        self.assertEqual(zc[0]["timestamp"], expected_event)

        # plate_reads at event epoch.
        pr = self.plate_reads()
        self.assertEqual(pr[0]["timestamp"], expected_event)

        # alerts at event epoch (AlertEngine reuses the same source timestamp).
        al = self.alerts()
        self.assertEqual(al[0]["timestamp"], expected_event)

        # The FakeANPR actually received exactly the mapped epoch.
        self.assertEqual(pipe.anpr.calls[-1][1], EPOCH0 + 3.0)
# ---------------------------------------------------------------------------
# 8. Duplicate suppression
# ---------------------------------------------------------------------------
class TestDuplicateSuppression(LivePipelineTestCase):
    def test_same_plate_not_persisted_or_alerted_twice(self):
        self.watchlist.add_watchlist_entry(
            WatchlistEntry(
                normalized_plate=PLATE,
                reason="R",
                category="STOLEN",
                priority="HIGH",
                active=True,
            )
        )
        result = ANPRResult(
            canonical_vehicle_id=100,
            vehicle_class="car",
            plate_text=PLATE,
            plate_detection_confidence=0.8,
            ocr_confidence=0.9,
            combined_confidence=0.72,
        )

        def scenario(frame, fn):
            return [make_vo(1, "car", (200, 200, 300, 400), frame_number=fn)]

        # ANPR returns the plate on EVERY frame.
        pipe = self.make_pipeline(
            tracker=FakeTracker(returns=scenario),
            anpr=FakeANPR(result=result, on_frames={1, 2, 3}),
        )
        pipe.process_frame(make_frame(), pts_ms=0.0)
        pipe.process_frame(make_frame(), pts_ms=1000.0)
        pipe.process_frame(make_frame(), pts_ms=2000.0)

        self.assertEqual(len(self.plate_reads()), 1)   # one row regardless
        self.assertEqual(len(self.alerts()), 1)        # one alert
        # first-observation event recorded exactly once
        det = [r for r in self.vehicle_events() if r["event_type"] == "DETECTED"]
        self.assertEqual(len(det), 1)

    def test_db_unique_index_guards_zone_reinsert(self):
        def scenario(frame, fn):
            if fn == 1:
                return [make_vo(1, "car", (20, 20, 40, 40), frame_number=fn)]  # outside
            return [make_vo(1, "car", (300, 300, 320, 320), frame_number=fn)]  # inside

        pipe = self.make_pipeline(tracker=FakeTracker(returns=scenario))
        pipe.process_frame(make_frame(), pts_ms=0.0)
        pipe.process_frame(make_frame(), pts_ms=1000.0)
        # Force a manual re-insert of the same zone count row -> ignored.
        from backend.db.models import ZoneCount

        self.recorder.record_zone_count(
            ZoneCount(
                camera_id="cam01",
                canonical_vehicle_id=100,
                vehicle_class="car",
                direction="IN",
                timestamp=_to_utc_iso(1700000001.0),
            )
        )
        self.assertEqual(len(self.zone_counts()), 1)


# ---------------------------------------------------------------------------
# 9. Graceful shutdown / run()
# ---------------------------------------------------------------------------
class TestGracefulShutdown(LivePipelineTestCase):
    def test_stop_releases_stream(self):
        stream = FakeStream([(True, make_frame(), 0.0), (True, make_frame(), 33.0)])
        pipe = self.make_pipeline(
            stream=stream,
            tracker=FakeTracker(returns=[]),
        )
        pipe.run(max_frames=2)
        self.assertTrue(pipe.stream.released)
        self.assertFalse(pipe._running)

    def test_stop_idempotent(self):
        stream = FakeStream([])
        pipe = self.make_pipeline(stream=stream)
        pipe.stop()
        pipe.stop()
        self.assertTrue(stream.released)