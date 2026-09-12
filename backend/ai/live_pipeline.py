"""
SentinelVision - Live AI Pipeline Orchestrator

Phase 8: connects the existing, already-tested Phase 1-7 modules into a
single end-to-end real-time pipeline.

Flow
----
    CameraStream                      (PTS-timed frame source)
        -> VehicleTracker             (YOLO11m + ByteTrack)   [Phase 1]
        -> VehicleClassStabilizer     (stable vehicle class)  [Phase 2]
        -> TrackContinuityManager     (canonical vehicle ids) [Phase 3]
        -> ZoneCounter                (directional IN/OUT)    [Phase 4]
        -> ANPREngine                 (detect + OCR + vote)   [Phase 5]
        -> EventRecorder              (SQLite repositories)   [Phase 6B]
        -> AlertEngine                (watchlist alerts)      [Phase 7]

Design rules (Phase 8)
----------------------
- This module ORCHESTRATES existing algorithms.  It never re-implements
  detection, tracking, stabilisation, continuity, counting, ANPR, or alert
  logic.
- No SQL lives here.  All persistence goes through
  ``backend.db.repositories.EventRecorder``.
- Event timestamps come from the camera PTS timeline, never from
  ``datetime.now()`` at event-processing time.  We anchor PTS once to a
  wall-clock epoch and derive every event epoch from that anchor, so the
  exact source timestamp propagates to every record.
- Camera credentials are handled exclusively by the central credential
  module; they are never logged, stored, or hard-coded here.

Testability
-----------
Every component is injectable.  Constructing ``LivePipeline`` with fakes
(detector/tracker/ANPR/CameraStream/repositories) makes it fully testable
without any GPU, camera, internet, or real credentials.  When components
are omitted, real ones are built from environment / default config for the
live ``python -m backend.ai.live_pipeline`` entry point.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from backend.camera.camera_stream import CameraStream
from backend.camera.rtsp_credentials import (
    DEFAULT_RTSP_HOST,
    DEFAULT_RTSP_PORT,
    fetch_camera_catalogue,
    get_catalogue_rtsp_url,
)
from backend.ai.anpr_engine import ANPREngine, ANPRResult, VehicleInfo
from backend.ai.plate_detector import build_real_plate_detector
from backend.ai.plate_ocr import EasyOCROCR
from backend.ai.track_continuity_manager import (
    CanonicalObservation,
    TrackContinuityManager,
    TrackObservation,
)
from backend.ai.vehicle_class_stabilizer import VehicleClassStabilizer
from backend.ai.vehicle_tracker import VehicleTracker
from backend.ai.zone_counter import CountingEvent, ZoneCounter, ZoneObservation
from backend.db.database import DEFAULT_DB_PATH, Database
from backend.db.models import Camera, PlateRead, VehicleEvent, ZoneCount
from backend.db.repositories import EventRecorder, GlobalVehicleRepository
from backend.services.alert_engine import AlertEngine

logger = logging.getLogger(__name__)

# Environment override for the database path (used by tests and runtime).
ENV_DB_PATH = "SENTINELVISION_DB_PATH"

# Default SQLite database location (Phase 6B default).
DEFAULT_DATABASE_PATH = DEFAULT_DB_PATH

# Default cam01 zone in NORMALISED coordinates (0..1 relative to frame).
# ZoneCounter operates in pixel space, so these are scaled by the frame
# resolution at connection time.  Easy to change per camera.
DEFAULT_ZONE: Tuple[float, float, float, float] = (0.10, 0.45, 0.90, 0.80)

# Vehicle lifecycle events we persist (Phase 6B vocabulary).
EVENT_FIRST_OBSERVED = "DETECTED"
EVENT_ZONE_IN = "ZONE_IN"
EVENT_ZONE_OUT = "ZONE_OUT"
class LivePipeline:
    """End-to-end orchestrator for the real-time AI pipeline.

    All the Phase 1-7 modules are composable and injectable.  Leaving any
    component ``None`` causes a real implementation to be built (required
    for the live entry point); tests inject fakes for camera/tracker/ANPR.

    Parameters
    ----------
    camera_id : str
        Dynamic camera identifier (e.g. ``"cam01"``).
    db_path : str, optional
        SQLite path.  Defaults to ``SENTINELVISION_DB_PATH`` env, else
        ``data/sentinelvision.db``.
    zone : tuple[float, float, float, float]
        Zone as normalised ``(x1, y1, x2, y2)`` in [0, 1], scaled to pix.
    stream : CameraStream, optional
        Frame source (default builds a real ``CameraStream``).
    tracker : VehicleTracker, optional
        ByteTrack wrapper (default builds real).
    stabilizer : VehicleClassStabilizer, optional
        Class stabiliser (default builds real).
    continuity : TrackContinuityManager, optional
        Canonical-ID continuity manager (default builds real).
    zone_counter : ZoneCounter, optional
        Pre-configured counter in pixel space.  When ``None`` one is built
        from ``zone`` scaled to the connected stream resolution.
    anpr : ANPREngine, optional
        ANPR engine (default builds real detector + EasyOCR).
    alert_engine : AlertEngine, optional
        Watchlist alert engine (default builds real against ``db``).
    recorder : EventRecorder, optional
        Persistence bridge (default builds real against ``db``).
    db : Database, optional
        Database abstraction (default builds real at ``db_path``).
    clock : callable, optional
        Wall-clock used to anchor the PTS timeline (default ``time.time``).
    stats_interval : int
        Frames between printed statistics (runtime only).
    display : bool
        Enable OpenCV overlay display window (runtime only).
    """

    def __init__(
        self,
        camera_id: str,
        *,
        db_path: Optional[str] = None,
        zone: Tuple[float, float, float, float] = DEFAULT_ZONE,
        stream: Optional[CameraStream] = None,
        tracker: Optional[VehicleTracker] = None,
        stabilizer: Optional[VehicleClassStabilizer] = None,
        continuity: Optional[TrackContinuityManager] = None,
        zone_counter: Optional[ZoneCounter] = None,
        anpr: Optional[ANPREngine] = None,
        alert_engine: Optional[AlertEngine] = None,
        recorder: Optional[EventRecorder] = None,
        db: Optional[Database] = None,
        clock: Optional[Callable[[], float]] = None,
        stats_interval: int = 200,
        display: bool = False,
        fetch_catalogue: bool = True,
    ) -> None:
        self.camera_id = str(camera_id)
        self.zone_normalized = tuple(float(v) for v in zone)
        self.stats_interval = int(stats_interval)
        self.display = bool(display)
        self.fetch_catalogue = bool(fetch_catalogue)
        self._clock: Callable[[], float] = clock if clock is not None else time.time

        # ---- database -----------------------------------------------------
        resolved_path = db_path or os.environ.get(ENV_DB_PATH) or DEFAULT_DATABASE_PATH
        self.db = db if db is not None else Database(str(resolved_path))
        # Idempotent: never deletes/resets existing tables.
        self.db.initialize()

        # ---- AI components (build real only when omitted) -----------------
        if tracker is None or stabilizer is None or continuity is None:
            tracker, stabilizer, continuity = self._build_real_ai(
                tracker=tracker, stabilizer=stabilizer, continuity=continuity
            )
        if anpr is None:
            anpr = self._build_real_anpr()

        self.tracker = tracker
        self.stabilizer = stabilizer
        self.continuity = continuity
        self.anpr = anpr

        # ZoneCounter is built lazily once the frame resolution is known
        # (ZoneCounter works in pixel space; ``zone`` is normalised).
        if zone_counter is not None:
            self.zone_counter = zone_counter
            self._pixel_zone = None
        else:
            self.zone_counter = None
            self._pixel_zone = None

        # ---- persistence / alerting ---------------------------------------
        self.recorder = recorder if recorder is not None else EventRecorder(self.db)
        self.alert_engine = (
            alert_engine if alert_engine is not None else AlertEngine(self.db)
        )
        self.global_vehicle_repo = GlobalVehicleRepository(self.db)
        self.stream = stream
# ---- runtime state -------------------------------------------------
        self.frames_processed = 0
        self.detections = 0
        self._active_raw_tracks = 0
        self._active_canonical = 0
        self.zone_in = 0
        self.zone_out = 0
        self.plate_detections = 0
        self.readable_plates = 0
        self.alerts = 0
        self._running = False

        # PTS -> epoch anchor (event timestamps come from here, never now())
        self._anchor_pts: Optional[float] = None
        # Dedup guards (session lifetime only; DB also has unique indexes)
        self._recorded_first: set = set()
        self._persisted_plates: set = set()

        # Last-frame data for display overlay / stats.
        self._last_display = None

    def reset_stream_state(self) -> None:
        """Reset internal tracker, stabilizer, continuity, and session dedup guards on video EOF loop."""
        if self.tracker is not None:
            try:
                self.tracker.reset()
            except Exception as exc:
                logger.debug("Tracker reset error: %s", exc)
        if self.stabilizer is not None:
            try:
                if hasattr(self.stabilizer, "reset"):
                    self.stabilizer.reset()
                elif hasattr(self.stabilizer, "_track_history"):
                    self.stabilizer._track_history.clear()
            except Exception as exc:
                logger.debug("Stabilizer reset error: %s", exc)
        if self.continuity is not None:
            try:
                if hasattr(self.continuity, "reset"):
                    self.continuity.reset()
                elif hasattr(self.continuity, "_active_tracks"):
                    self.continuity._active_tracks.clear()
            except Exception as exc:
                logger.debug("Continuity reset error: %s", exc)
        self._recorded_first.clear()
        self._persisted_plates.clear()

    # ------------------------------------------------------------------
    # Real component builders (live runtime; not used by mocked tests)
    # ------------------------------------------------------------------
    @staticmethod
    def _build_real_ai(
        tracker: Optional[VehicleTracker],
        stabilizer: Optional[VehicleClassStabilizer],
        continuity: Optional[TrackContinuityManager],
    ) -> Tuple[VehicleTracker, VehicleClassStabilizer, TrackContinuityManager]:
        """Construct real Phase 1-3 pipeline components."""
        if tracker is None:
            tracker = VehicleTracker()
        if stabilizer is None:
            stabilizer = VehicleClassStabilizer()
        if continuity is None:
            continuity = TrackContinuityManager()
        return tracker, stabilizer, continuity

    @staticmethod
    def _build_real_anpr() -> ANPREngine:
        """Construct the real Phase 5 ANPR engine (detector + EasyOCR)."""
        return ANPREngine(build_real_plate_detector(), EasyOCROCR())

    # ------------------------------------------------------------------
    # PTS -> epoch mapping
    # ------------------------------------------------------------------
    def map_pts_to_epoch(self, pts_ms: Optional[float]) -> Optional[float]:
        """Convert a camera PTS (milliseconds) into a wall-clock epoch.

        The first observed PTS anchors to the current wall clock; every
        subsequent PTS is mapped by adding the PTS delta.  This guarantees
        event timestamps always originate from the camera PTS timeline and
        are never replaced with ``datetime.now()`` at event time.
        """
        if pts_ms is None:
            return None
        pts = float(pts_ms)
        if self._anchor_pts is None:
            self._anchor_pts = pts
            self._anchor_epoch = float(self._clock())
        return self._anchor_epoch + (pts - self._anchor_pts) / 1000.0
# ------------------------------------------------------------------
    # Zone setup
    # ------------------------------------------------------------------
    def _ensure_zone(self, resolution: Optional[Tuple[int, int]]) -> ZoneCounter:
        """Return the configured ZoneCounter, building a pixel-space one
        from the normalised zone when none was injected."""
        if self.zone_counter is not None:
            return self.zone_counter
        if resolution is None:
            w = h = 1920  # fallback if resolution is unavailable
        else:
            w, h = resolution
        x1, y1, x2, y2 = self.zone_normalized
        self._pixel_zone = (x1 * w, y1 * h, x2 * w, y2 * h)
        self.zone_counter = ZoneCounter(tuple(self._pixel_zone))
        return self.zone_counter

    # ------------------------------------------------------------------
    # Camera registration (Phase 6B/9)
    # ------------------------------------------------------------------
    @staticmethod
    def _credential_free_rtsp(camera_id: str) -> str:
        return f"rtsp://{DEFAULT_RTSP_HOST}:{DEFAULT_RTSP_PORT}/stream/{camera_id}"

    def _register_camera(
        self,
        resolution: Optional[Tuple[int, int]],
        name: Optional[str] = None,
    ) -> None:
        """Upsert the camera row (credential-free) via the repository."""
        camera = Camera(
            camera_id=self.camera_id,
            rtsp_url=self._credential_free_rtsp(self.camera_id),
            live=True,
        )
        if resolution is not None:
            camera.width, camera.height = int(resolution[0]), int(resolution[1])
        if name:
            camera.name = name
        try:
            self.recorder.register_camera(camera)
            logger.info("Camera '%s' registered (credential-free URL).", self.camera_id)
        except Exception as exc:  # defensive: never abort the pipeline
            logger.warning("Camera registration failed for '%s': %s", self.camera_id, exc)

    def _fetch_camera_name(self) -> Optional[str]:
        """Best-effort, credential-free catalogue lookup for the camera name."""
        try:
            catalogue = fetch_camera_catalogue(timeout=5)
            base = get_catalogue_rtsp_url(self.camera_id, catalogue)
            if base is None:
                return None
            return base.split("rtsp://")[-1].split("/")[0]
        except Exception:  # noqa: BLE001
            return None
# ------------------------------------------------------------------
    # Main run loop (runtime entry)
    # ------------------------------------------------------------------
    def run(self, max_frames: int = 0, duration: Optional[float] = None) -> None:
        """Connect to the camera and process live frames.

        Parameters
        ----------
        max_frames : int
            Stop after this many frames (0 = unlimited).
        duration : float, optional
            Stop after this many seconds (``None`` = run until stopped).
        """
        if self.stream is None:
            self.stream = CameraStream(self.camera_id)

        if not self.stream.connect():
            logger.error("Could not open camera '%s'.", self.camera_id)
            return

        resolution = self.stream.resolution
        self._ensure_zone(resolution)
        name = self._fetch_camera_name() if self.fetch_catalogue else None
        self._register_camera(resolution, name=name)
        self._log_startup(resolution)

        self._running = True
        start = time.monotonic()
        import cv2  # local import keeps headless/import-light usage

        try:
            while self._running:
                ok, frame, pts_ms = self.stream.read()
                if not ok or frame is None:
                    # Inter-frame gaps are normal (CameraStream reconnects).
                    continue

                self.process_frame(frame, pts_ms)

                if self.display:
                    if self._last_display is not None:
                        display = self._render(*self._last_display)
                        cv2.imshow(self.camera_id, display)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), ord("Q"), 27):  # q / ESC
                        break

                if self.stats_interval and self.frames_processed % self.stats_interval == 0:
                    self._print_stats(final=False)

                if max_frames and self.frames_processed >= max_frames:
                    break
                if duration and (time.monotonic() - start) >= duration:
                    break
        except KeyboardInterrupt:
            logger.info("Interrupted - stopping pipeline.")
        finally:
            self.stop()
            if self.display:
                cv2.destroyAllWindows()

        self._print_stats(final=True)

    # ------------------------------------------------------------------
    # Per-frame processing (testable in isolation)
    # ------------------------------------------------------------------
    def process_frame(
        self,
        frame,
        pts_ms: Optional[float] = None,
    ) -> List[CanonicalObservation]:
        """Process a single frame through the whole Phase 1-7 pipeline.

        Parameters
        ----------
        frame : numpy.ndarray
            BGR frame.
        pts_ms : float, optional
            Camera PTS timestamp in milliseconds (event timing source).

        Returns
        -------
        list[CanonicalObservation]
            Canonical vehicle observations seen this frame.
        """
        self.frames_processed += 1
        frame_number = self.frames_processed
        epoch = self.map_pts_to_epoch(pts_ms)

        # ---- 1) detect + track (Phase 1) ----------------------------------
        observations = self.tracker.track(frame, frame_number)
        self.detections += len(observations)
        self._active_raw_tracks = len({o.raw_track_id for o in observations})

        # ---- 2) stabilise class (Phase 2) ---------------------------------
        stable_class: Dict[int, str] = {}
        active_ids = {o.raw_track_id for o in observations}
        for obs in observations:
            sclass, _ = self.stabilizer.update(
                obs.raw_track_id, obs.class_name, obs.confidence
            )
            stable_class[obs.raw_track_id] = sclass or obs.class_name
        self.stabilizer.cleanup(active_ids)

        # ---- 3) canonical continuity (Phase 3) -----------------------------
        track_observations = [
            TrackObservation(
                raw_track_id=o.raw_track_id,
                class_name=stable_class.get(o.raw_track_id, o.class_name),
                bbox=o.bbox,
                center=o.center,
                frame_number=frame_number,
            )
            for o in observations
        ]
        canonical = self.continuity.update(track_observations, frame_number)
        self._active_canonical = len({co.canonical_id for co in canonical})

        # ---- 4) zone counting + events (Phase 4 / STEP 4 & 5) -------------
        self._process_zone(canonical, epoch, frame_number)

        # ---- 5) first-observation lifecycle event (STEP 5) ----------------
        self._record_first_observations(canonical, epoch)

        # ---- 6) ANPR + plate reads + alerts (Phase 5/6B/7) ----------------
        plate_results = self._process_anpr(frame, canonical, epoch, frame_number)

        # ---- housekeeping --------------------------------------------------
        self.continuity.cleanup()
        if self.zone_counter is not None:
            try:
                self.zone_counter.cleanup(frame_number)
            except Exception:  # noqa: BLE001
                pass

        if self.display:
            self._last_display = (frame, observations, canonical, plate_results)

        return canonical
# ------------------------------------------------------------------
    # Zone + lifecycle event recording
    # ------------------------------------------------------------------
    def _process_zone(
        self,
        canonical: List[CanonicalObservation],
        epoch: Optional[float],
        frame_number: int,
    ) -> List[CountingEvent]:
        if self.zone_counter is None:
            return []
        events: List[CountingEvent] = []
        for co in canonical:
            try:
                event = self.zone_counter.update(
                    ZoneObservation(
                        canonical_id=co.canonical_id,
                        vehicle_class=co.class_name,
                        center=co.center,
                        frame_number=frame_number,
                    )
                )
            except Exception:  # noqa: BLE001 - never abort a frame
                continue
            if event is None:
                continue
            events.append(event)
            self._record_zone_event(event, epoch)
        return events

    def _record_zone_event(self, event: CountingEvent, epoch: Optional[float]) -> None:
        direction = event.direction
        event_type = EVENT_ZONE_IN if direction == "IN" else EVENT_ZONE_OUT

        # Increment counters only for genuinely confirmed transitions.
        if direction == "IN":
            self.zone_in += 1
        else:
            self.zone_out += 1

        # zone_counts (Phase 4/6B) - DB unique index suppresses duplicates.
        try:
            self.recorder.record_zone_count(
                ZoneCount(
                    camera_id=self.camera_id,
                    canonical_vehicle_id=event.canonical_vehicle_id,
                    vehicle_class=event.vehicle_class,
                    direction=direction,
                    timestamp=epoch,
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to record zone_count event.")

        # vehicle_events lifecycle log (Phase 6B).
        try:
            self.recorder.record_vehicle_event(
                VehicleEvent(
                    canonical_vehicle_id=event.canonical_vehicle_id,
                    camera_id=self.camera_id,
                    vehicle_class=event.vehicle_class,
                    event_type=event_type,
                    direction=direction,
                    timestamp=epoch,
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to record vehicle_events entry.")

    def _record_first_observations(
        self,
        canonical: List[CanonicalObservation],
        epoch: Optional[float],
    ) -> None:
        for co in canonical:
            if co.canonical_id in self._recorded_first:
                continue
            self._recorded_first.add(co.canonical_id)
            try:
                self.recorder.record_vehicle_event(
                    VehicleEvent(
                        canonical_vehicle_id=co.canonical_id,
                        camera_id=self.camera_id,
                        vehicle_class=co.class_name,
                        event_type=EVENT_FIRST_OBSERVED,
                        timestamp=epoch,
                    )
                )
            except Exception:  # noqa: BLE001
                logger.warning("Failed to record first-observation event.")
# ------------------------------------------------------------------
    # ANPR + plate read + alert flow (STEP 6 & 7)
    # ------------------------------------------------------------------
    def _process_anpr(
        self,
        frame,
        canonical: List[CanonicalObservation],
        epoch: Optional[float],
        frame_number: int,
    ) -> List[ANPRResult]:
        if not canonical:
            return []

        vehicle_infos = [
            VehicleInfo(
                canonical_id=co.canonical_id,
                bbox=co.bbox,
                class_name=co.class_name,
            )
            for co in canonical
        ]

        try:
            results = self.anpr.process_frame(
                frame, vehicle_infos, frame_number=frame_number, timestamp=epoch
            )
        except Exception:  # noqa: BLE001 - ANPR never aborts the pipeline
            logger.warning("ANPR processing failed for frame %d.", frame_number)
            return []

        for result in results:
            if result is None or not result.plate_text:
                continue
            self.plate_detections += 1
            self._record_plate_read(result, epoch)

        return results

    def _record_plate_read(self, result: ANPRResult, epoch: Optional[float]) -> None:
        # Do not persist (or alert on) the same finalized plate repeatedly.
        key = (result.canonical_vehicle_id, result.plate_text)
        if key in self._persisted_plates:
            return
        self._persisted_plates.add(key)

        plate_read = PlateRead(
            canonical_vehicle_id=result.canonical_vehicle_id,
            camera_id=self.camera_id,
            raw_ocr=result.plate_text,
            timestamp=epoch,
            normalized_plate=result.plate_text,
            ocr_confidence=result.ocr_confidence,
            detector_confidence=result.plate_detection_confidence,
            combined_confidence=result.combined_confidence,
        )

        try:
            plate_read_id = self.recorder.record_plate_read(plate_read)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to record plate_read.")
            return

        # Only alert when the plate read was newly persisted (not a dup).
        if plate_read_id is None:
            return
        self.readable_plates += 1

        try:
            self.global_vehicle_repo.record_plate_observation(
                plate=result.plate_text,
                camera_id=self.camera_id,
                canonical_vehicle_id=result.canonical_vehicle_id,
                vehicle_class=result.vehicle_class,
                timestamp=epoch,
                plate_read_id=plate_read_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning("GlobalVehicle observation recording failed.")

        try:
            alert = self.alert_engine.process_plate_read(
                plate=result.plate_text,
                canonical_vehicle_id=result.canonical_vehicle_id,
                camera_id=self.camera_id,
                plate_read_id=plate_read_id,
                vehicle_class=result.vehicle_class,
                confidence=result.combined_confidence,
                timestamp=epoch,
            )
        except Exception:  # noqa: BLE001
            logger.warning("AlertEngine processing failed.")
            return

        if alert is not None:
            self.alerts += 1
# ------------------------------------------------------------------
    # Runtime statistics / display / shutdown
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, object]:
        """Return a snapshot of runtime statistics (informational only)."""
        return {
            "camera_id": self.camera_id,
            "frames": self.frames_processed,
            "detections": self.detections,
            "raw_tracks": self._active_raw_tracks,
            "canonical_tracks": self._active_canonical,
            "zone_in": self.zone_in,
            "zone_out": self.zone_out,
            "plate_detections": self.plate_detections,
            "readable_plates": self.readable_plates,
            "alerts": self.alerts,
        }

    def _log_startup(self, resolution: Optional[Tuple[int, int]]) -> None:
        info = {}
        try:
            info = self.tracker.get_device_info()
        except Exception:  # noqa: BLE001
            info = {}
        logger.info(
            "Starting live pipeline camera=%s resolution=%s device=%s zone=%s",
            self.camera_id,
            resolution,
            info.get("gpu_name", "?"),
            self._pixel_zone if self._pixel_zone else self.zone_normalized,
        )

    def _gpu_label(self) -> str:
        try:
            info = self.tracker.get_device_info()
            return str(info.get("gpu_name", "n/a"))
        except Exception:  # noqa: BLE001
            return "n/a"

    def _print_stats(self, final: bool = False) -> None:
        s = self.get_stats()
        logger.info("=" * 60)
        if final:
            logger.info("SENTINELVISION LIVE PIPELINE")
        logger.info("Camera: %s", s["camera_id"])
        logger.info("GPU: %s", self._gpu_label())
        logger.info("")
        logger.info("Frames: %d", s["frames"])
        logger.info("Vehicle detections: %d", s["detections"])
        logger.info("Raw tracks: %d", s["raw_tracks"])
        logger.info("Canonical tracks: %d", s["canonical_tracks"])
        logger.info("")
        logger.info("Zone:")
        logger.info("  IN: %d", s["zone_in"])
        logger.info("  OUT: %d", s["zone_out"])
        logger.info("")
        logger.info("ANPR:")
        logger.info("  Plate detections: %d", s["plate_detections"])
        logger.info("  Readable plates: %d", s["readable_plates"])
        logger.info("")
        logger.info("Alerts: %d", s["alerts"])
        logger.info("")
        logger.info("Press Q or Ctrl+C to stop.")
        logger.info("=" * 60)

    def _render(self, frame, observations, canonical, plate_results):
        """Draw vehicle boxes, IDs, class + zone overlay (display only)."""
        import cv2

        display = frame.copy()
        w, h = display.shape[1], display.shape[0]
        x1, y1, x2, y2 = self._pixel_zone or (0, 0, w, h)
        cv2.rectangle(display, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)
        color_by_class = {
            "car": (255, 0, 0),
            "motorcycle": (0, 255, 0),
            "bus": (0, 128, 255),
            "truck": (255, 128, 0),
        }
        canonical_by_bt = {co.bytetrack_id: co for co in canonical}
        plate_by_canonical = {r.canonical_vehicle_id: r for r in plate_results}

        for obs in observations:
            bx1, by1, bx2, by2 = (int(v) for v in obs.bbox)
            color = color_by_class.get(obs.class_name, (0, 255, 255))
            cv2.rectangle(display, (bx1, by1), (bx2, by2), color, 2)
            co = canonical_by_bt.get(obs.raw_track_id)
            cid = co.canonical_id if co else "?"
            label = f"R{obs.raw_track_id} C{cid} {obs.class_name}"
            pr = plate_by_canonical.get(cid) if co else None
            if pr is not None:
                label += f" {pr.plate_text}"
            cv2.putText(
                display,
                label,
                (bx1, max(15, by1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
            )
        return display

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Idempotently stop frame processing and release resources."""
        self._running = False
        if self.stream is not None:
            try:
                self.stream.release()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> "LivePipeline":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# CLI entry point:  python -m backend.ai.live_pipeline --camera cam01
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SentinelVision Live AI Pipeline")
    parser.add_argument("--camera", type=str, default="cam01", help="Camera ID (default: cam01)")
    parser.add_argument("--display", action="store_true", help="Show OpenCV overlay window")
    parser.add_argument("--frames", type=int, default=0, help="Max frames (0 = unlimited)")
    parser.add_argument(
        "--seconds", type=float, default=0.0, help="Max duration in seconds (0 = unlimited)"
    )
    parser.add_argument("--db", type=str, default=None, help="SQLite db path override")
    parser.add_argument(
        "--zone",
        type=float,
        nargs=4,
        default=list(DEFAULT_ZONE),
        metavar=("X1", "Y1", "X2", "Y2"),
        help="Normalised zone x1 y1 x2 y2 (default: 0.10 0.45 0.90 0.80)",
    )
    parser.add_argument("--stats-interval", type=int, default=200, help="Stats print interval")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    pipeline = LivePipeline(
        camera_id=args.camera,
        db_path=args.db,
        zone=tuple(args.zone),
        stats_interval=args.stats_interval,
        display=args.display,
    )
    pipeline.run(max_frames=args.frames, duration=args.seconds or None)


if __name__ == "__main__":
    main()