"""
SentinelVision - Multi-Camera Ingestion Manager

Phase N: Real Multi-Camera Ingestion & Cross-Camera Vehicle Pipeline Feeder

Responsibilities
----------------
- Manage lifecycle for multiple concurrent camera ingestion workers (RTSP or video files).
- Multi-threaded worker execution with thread isolation: one worker failing does not crash others.
- Bounded concurrency limit (MAX_AI_WORKERS) to protect GPU/CPU/VRAM resources.
- Direct integration with LivePipeline / CameraStream to process frames through existing AI components.
- Automatic persistence of GlobalVehicle and CrossCameraObservation records on plate detection.
- Sync runtime camera stream health with CameraHealthRepository.
- Thread-safe worker starting, stopping, and telemetry status queries.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from backend.ai.live_pipeline import LivePipeline
from backend.camera.camera_stream import CameraStream
from backend.db.database import Database, DEFAULT_DB_PATH
from backend.db.repositories import EventRecorder, GlobalVehicleRepository, CameraHealthRepository
from backend.db.models import CameraHealth

logger = logging.getLogger("sentinelvision.multi_ingestion")

# Maximum concurrent active AI worker streams allowed (default small for RTX 3050 protection)
DEFAULT_MAX_AI_WORKERS = int(os.environ.get("SENTINEL_MAX_AI_WORKERS", "3"))


@dataclass
class CameraWorkerConfig:
    camera_id: str
    source_type: str = "rtsp"  # "rtsp" or "video"
    video_path: Optional[str] = None
    zone: Tuple[float, float, float, float] = (0.10, 0.45, 0.90, 0.80)
    display: bool = False


@dataclass
class CameraWorkerStatus:
    camera_id: str
    running: bool
    status: str  # "STARTING", "ONLINE", "DEGRADED", "OFFLINE", "STOPPED", "ERROR"
    frames_processed: int = 0
    detections: int = 0
    readable_plates: int = 0
    alerts: int = 0
    last_error: Optional[str] = None
    source_type: str = "rtsp"


class CameraIngestionWorker:
    """Individual background worker thread for one camera stream."""

    def __init__(
        self,
        config: CameraWorkerConfig,
        db: Database,
        pipeline_factory: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.camera_id = config.camera_id
        self.db = db
        self._pipeline_factory = pipeline_factory
        
        self.health_repo = CameraHealthRepository(self.db)
        self.global_vehicle_repo = GlobalVehicleRepository(self.db)
        self.recorder = EventRecorder(self.db)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.pipeline: Optional[LivePipeline] = None
        
        self.status = "STOPPED"
        self.last_error: Optional[str] = None
        self.frames_processed = 0

    def start(self) -> None:
        """Start the camera worker background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Worker for camera '%s' is already running.", self.camera_id)
            return

        self._stop_event.clear()
        self.status = "STARTING"
        self.health_repo.upsert_health(
            CameraHealth(camera_id=self.camera_id, status="NOT_CHECKED", last_error=None)
        )

        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"CameraWorker-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Camera worker thread started for camera '%s'", self.camera_id)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal worker to stop and wait for thread join."""
        self._stop_event.set()
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            logger.info("Camera worker thread joined for camera '%s'", self.camera_id)

        self.status = "STOPPED"

    def _run_loop(self) -> None:
        """Background thread main execution loop."""
        import cv2

        try:
            # Auto-resolve virtual camera video source if needed
            from backend.camera.camera_catalogue import get_virtual_video_path
            if self.camera_id.startswith("v_cam") and not self.config.video_path:
                resolved_vpath = get_virtual_video_path(self.camera_id)
                if resolved_vpath:
                    self.config.source_type = "video"
                    self.config.video_path = resolved_vpath

            # Construct frame stream source (Video file or RTSP stream)
            if self.config.source_type == "video" and self.config.video_path:
                if not os.path.exists(self.config.video_path):
                    err_msg = f"Video file not found: {self.config.video_path}"
                    logger.error("[%s] %s", self.camera_id, err_msg)
                    self.status = "ERROR"
                    self.last_error = err_msg
                    self.health_repo.record_failure(self.camera_id, error_msg=err_msg)
                    return

                cap = cv2.VideoCapture(self.config.video_path)
                if not cap.isOpened():
                    err_msg = f"Failed to open video file: {self.config.video_path}"
                    logger.error("[%s] %s", self.camera_id, err_msg)
                    self.status = "ERROR"
                    self.last_error = err_msg
                    self.health_repo.record_failure(self.camera_id, error_msg=err_msg)
                    return

                # Create custom CameraStream wrapper for video file
                stream = CameraStream(self.camera_id, capture_factory=lambda _url: cap)
                stream._capture = cap
            else:
                stream = CameraStream(self.camera_id)
                if not stream.connect(max_attempts=3):
                    err_msg = f"Failed to connect RTSP stream for {self.camera_id}"
                    logger.warning("[%s] %s", self.camera_id, err_msg)
                    self.status = "OFFLINE"
                    self.last_error = err_msg
                    self.health_repo.record_failure(self.camera_id, error_msg=err_msg)
                    return

            # Construct LivePipeline
            if self._pipeline_factory:
                self.pipeline = self._pipeline_factory(self.camera_id, stream=stream)
            else:
                self.pipeline = LivePipeline(
                    camera_id=self.camera_id,
                    db=self.db,
                    stream=stream,
                    zone=self.config.zone,
                    display=self.config.display,
                    fetch_catalogue=False,
                )

            # Register camera row in DB
            res = stream.resolution or (1920, 1080)
            self.pipeline._register_camera(res)
            self.pipeline._ensure_zone(res)

            self.status = "ONLINE"
            self.health_repo.record_success(self.camera_id)

            fps = cap.get(cv2.CAP_PROP_FPS) if (self.config.source_type == "video" and cap) else 30.0
            if not fps or fps <= 0:
                fps = 30.0
            frame_delay = 1.0 / fps

            start_wall_time = time.time()
            pts_counter_ms = 0.0

            while not self._stop_event.is_set():
                if self.config.source_type == "video":
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        # Loop video file for continuous worker processing
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        if self.pipeline:
                            try:
                                self.pipeline.reset_stream_state()
                            except Exception as reset_err:
                                logger.warning("[%s] Reset stream state error on loop: %s", self.camera_id, reset_err)
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break
                    pts_counter_ms += (1000.0 / fps)
                    pts_ms = pts_counter_ms
                else:
                    ok, frame, pts_ms = stream.read()
                    if not ok or frame is None:
                        if stream._consecutive_read_failures > 5:
                            self.status = "DEGRADED"
                            self.health_repo.record_failure(
                                self.camera_id,
                                error_msg=f"Read failure count {stream._consecutive_read_failures}",
                            )
                        time.sleep(0.05)
                        continue

                # Process single frame through AI pipeline
                self.pipeline.process_frame(frame, pts_ms)
                self.frames_processed = self.pipeline.frames_processed

                # Periodically sync health & success status
                if self.frames_processed % 30 == 0:
                    self.status = "ONLINE"
                    self.health_repo.record_success(self.camera_id)

                # Frame rate throttling for video sources
                if self.config.source_type == "video":
                    time.sleep(frame_delay * 0.5)

        except Exception as exc:
            err = f"Worker exception: {exc}"
            logger.exception("[%s] %s", self.camera_id, err)
            self.status = "ERROR"
            self.last_error = err
            self.health_repo.record_failure(self.camera_id, error_msg=err)
        finally:
            self.status = "STOPPED"
            if self.pipeline:
                try:
                    self.pipeline.stop()
                except Exception:
                    pass

    def get_status(self) -> CameraWorkerStatus:
        stats = self.pipeline.get_stats() if self.pipeline else {}
        return CameraWorkerStatus(
            camera_id=self.camera_id,
            running=self._thread is not None and self._thread.is_alive(),
            status=self.status,
            frames_processed=self.frames_processed,
            detections=int(stats.get("detections", 0)),
            readable_plates=int(stats.get("readable_plates", 0)),
            alerts=int(stats.get("alerts", 0)),
            last_error=self.last_error,
            source_type=self.config.source_type,
        )


class MultiCameraIngestionManager:
    """Orchestrator for managing multiple background ingestion workers safely."""

    def __init__(
        self,
        db: Optional[Database] = None,
        db_path: Optional[str] = None,
        max_workers: int = DEFAULT_MAX_AI_WORKERS,
    ) -> None:
        resolved_path = db_path or os.environ.get("SENTINELVISION_DB_PATH") or DEFAULT_DB_PATH
        self.db = db if db is not None else Database(str(resolved_path))
        self.db.initialize()
        
        self.max_workers = max(1, int(max_workers))
        self.workers: Dict[str, CameraIngestionWorker] = {}
        self._lock = threading.Lock()

    def start_camera_worker(
        self,
        config: CameraWorkerConfig,
        pipeline_factory: Optional[Any] = None,
    ) -> bool:
        """Start a worker for a specific camera if under max_workers limit."""
        with self._lock:
            # Check if camera worker already running
            if config.camera_id in self.workers:
                worker = self.workers[config.camera_id]
                if worker._thread and worker._thread.is_alive():
                    logger.info("Worker for camera '%s' already running.", config.camera_id)
                    return True

            # Count active running workers
            active_workers = [
                (cid, w) for cid, w in list(self.workers.items()) if w._thread and w._thread.is_alive()
            ]
            if len(active_workers) >= self.max_workers:
                # Evict non-selected active worker(s) to make room for newly requested camera
                for cid, worker_to_stop in active_workers:
                    if cid != config.camera_id:
                        logger.info("Evicting worker for camera '%s' to launch '%s'", cid, config.camera_id)
                        worker_to_stop.stop()
                        del self.workers[cid]
                        break

            worker = CameraIngestionWorker(config, db=self.db, pipeline_factory=pipeline_factory)
            self.workers[config.camera_id] = worker
            worker.start()
            return True

    def stop_camera_worker(self, camera_id: str) -> bool:
        """Stop worker for a specific camera."""
        with self._lock:
            if camera_id not in self.workers:
                return False
            worker = self.workers[camera_id]
            worker.stop()
            del self.workers[camera_id]
            return True

    def stop_all(self) -> None:
        """Stop all running camera workers cleanly."""
        with self._lock:
            for cam_id, worker in list(self.workers.items()):
                worker.stop()
            self.workers.clear()

    def get_worker_statuses(self) -> List[CameraWorkerStatus]:
        """Get telemetry status list for all managed workers."""
        with self._lock:
            return [w.get_status() for w in self.workers.values()]

    def get_active_worker_count(self) -> int:
        """Return total currently running worker threads."""
        with self._lock:
            return sum(1 for w in self.workers.values() if w._thread and w._thread.is_alive())


# Global multi-camera manager instance
global_ingestion_manager = MultiCameraIngestionManager()
