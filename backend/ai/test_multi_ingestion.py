"""
Unit and integration tests for Phase N: Multi-Camera Ingestion Manager & Cross-Camera Pipeline
"""

import os
import time
import pytest
from unittest.mock import MagicMock

from backend.ai.multi_ingestion import (
    CameraIngestionWorker,
    CameraWorkerConfig,
    MultiCameraIngestionManager,
)
from backend.db.database import Database
from backend.db.repositories import (
    CameraHealthRepository,
    GlobalVehicleRepository,
    EventRecorder,
)
from backend.db.models import Camera, PlateRead


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_multi_ingestion.db"
    db = Database(str(db_file))
    db.initialize()
    return db


def test_worker_config_and_initialization(temp_db):
    config = CameraWorkerConfig(camera_id="cam01", source_type="rtsp")
    worker = CameraIngestionWorker(config, temp_db)
    assert worker.camera_id == "cam01"
    assert worker.status == "STOPPED"
    assert worker.frames_processed == 0


def test_multi_ingestion_manager_max_workers(temp_db):
    manager = MultiCameraIngestionManager(db=temp_db, max_workers=2)
    assert manager.max_workers == 2
    assert manager.get_active_worker_count() == 0

    # Mock pipeline factory
    mock_factory = MagicMock()
    mock_pipeline = MagicMock()
    mock_pipeline.get_stats.return_value = {"detections": 5, "readable_plates": 1}
    mock_factory.return_value = mock_pipeline

    cfg1 = CameraWorkerConfig(camera_id="cam01", source_type="video", video_path="nonexistent.mp4")
    cfg2 = CameraWorkerConfig(camera_id="cam02", source_type="video", video_path="nonexistent.mp4")
    cfg3 = CameraWorkerConfig(camera_id="cam03", source_type="video", video_path="nonexistent.mp4")

    # Start 2 workers
    started1 = manager.start_camera_worker(cfg1, pipeline_factory=mock_factory)
    started2 = manager.start_camera_worker(cfg2, pipeline_factory=mock_factory)
    assert started1 is True
    assert started2 is True

    # 3rd worker evicts older inactive worker so newly selected camera gets worker, maintaining max_workers = 2
    started3 = manager.start_camera_worker(cfg3, pipeline_factory=mock_factory)
    assert started3 is True
    assert manager.get_active_worker_count() <= 2

    manager.stop_all()
    assert manager.get_active_worker_count() == 0


def test_worker_failure_isolation(temp_db):
    """Verify one worker failure does not crash manager or other workers."""
    manager = MultiCameraIngestionManager(db=temp_db, max_workers=3)

    cfg_bad = CameraWorkerConfig(camera_id="cam_bad", source_type="video", video_path="non_existent_file.mp4")
    
    started = manager.start_camera_worker(cfg_bad)
    assert started is True

    time.sleep(0.5)

    statuses = manager.get_worker_statuses()
    bad_status = next(s for s in statuses if s.camera_id == "cam_bad")
    assert bad_status.running is False
    assert bad_status.status in ("ERROR", "STOPPED")
    assert bad_status.last_error is not None

    manager.stop_all()


def test_cross_camera_observation_integration(temp_db):
    """Deterministic integration test simulating Camera A and Camera B recording the same plate."""
    gv_repo = GlobalVehicleRepository(temp_db)
    recorder = EventRecorder(temp_db)

    # Register cameras
    recorder.register_camera(Camera(camera_id="cam01", live=True))
    recorder.register_camera(Camera(camera_id="cam05", live=True))

    target_plate = "GJ01AB1234"
    ts1 = "2026-09-11T10:00:00.000000+00:00"
    ts2 = "2026-09-11T10:05:00.000000+00:00"

    # Camera 1 reads plate
    read1 = PlateRead(
        canonical_vehicle_id=101,
        camera_id="cam01",
        raw_ocr=target_plate,
        normalized_plate=target_plate,
        timestamp=ts1,
        combined_confidence=0.92,
    )
    r1_id = recorder.record_plate_read(read1)
    gv_repo.record_plate_observation(
        plate=target_plate,
        camera_id="cam01",
        canonical_vehicle_id=101,
        vehicle_class="car",
        timestamp=ts1,
        plate_read_id=r1_id,
    )

    # Camera 5 reads same plate 5 mins later
    read2 = PlateRead(
        canonical_vehicle_id=202,
        camera_id="cam05",
        raw_ocr=target_plate,
        normalized_plate=target_plate,
        timestamp=ts2,
        combined_confidence=0.95,
    )
    r2_id = recorder.record_plate_read(read2)
    gv_repo.record_plate_observation(
        plate=target_plate,
        camera_id="cam05",
        canonical_vehicle_id=202,
        vehicle_class="car",
        timestamp=ts2,
        plate_read_id=r2_id,
    )

    # Verify GlobalVehicle lookup
    gv = gv_repo.get_global_vehicle_by_plate(target_plate)
    assert gv is not None
    assert gv.normalized_plate == target_plate
    assert gv.first_seen_at == ts1
    assert gv.last_seen_at == ts2

    # Verify chronological observations timeline
    timeline = gv_repo.get_timeline(gv.global_vehicle_id)
    assert len(timeline) == 2
    assert timeline[0].camera_id == "cam01"
    assert timeline[0].timestamp == ts1
    assert timeline[1].camera_id == "cam05"
    assert timeline[1].timestamp == ts2
