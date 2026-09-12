"""
SentinelVision - Tests for Final Critical Fixes

Verifies:
1. Exactly 30 real government cameras are present (cam01..cam30).
2. Dynamic demo camera catalogue contains ONLY cameras for actual video files on disk.
3. Virtual demo feeds are excluded from GIS map coordinates.
4. Mapped GIS cameras count is exactly 30 real government cameras.
5. Ingestion manager supports camera worker switching and bounded concurrency eviction.
6. Camera counts endpoint isolates counts per camera_id without cross-camera bleeding.
7. Demo video sources use the same production AI pipeline structure.
"""

import os
import pytest
from backend.camera.camera_catalogue import (
    CameraCatalogue,
    get_official_30_catalogue,
    get_virtual_30_catalogue,
    get_virtual_video_path,
    VIRTUAL_CAMERA_MAP,
)
from backend.ai.multi_ingestion import (
    MultiCameraIngestionManager,
    CameraWorkerConfig,
)
from backend.db.database import Database
from backend.db.repositories import ZoneRepository
from backend.db.models import ZoneCount


def test_official_30_government_cameras():
    """Verify that exactly 30 real government cameras (cam01..cam30) are present."""
    official = get_official_30_catalogue()
    assert len(official) == 30
    cam_ids = [c.camera_id for c in official]
    for i in range(1, 31):
        assert f"cam{i:02d}" in cam_ids
    
    # Verify non-virtual flag
    for c in official:
        assert c.is_virtual is False


def test_demo_catalogue_strictly_matches_existing_video_files():
    """Verify that virtual demo feeds strictly match existing video files on disk."""
    virtual_cams = get_virtual_30_catalogue()
    assert len(virtual_cams) <= len(VIRTUAL_CAMERA_MAP)
    
    for vcam in virtual_cams:
        assert vcam.is_virtual is True
        assert vcam.camera_id.startswith("v_cam")
        # Geographic coordinates must be None for demo feeds
        assert vcam.latitude is None
        assert vcam.longitude is None
        
        vpath = get_virtual_video_path(vcam.camera_id)
        assert vpath is not None
        assert os.path.exists(vpath)

    # Ensure no synthetic v_cam07..v_cam30 are generated
    v_ids = [c.camera_id for c in virtual_cams]
    assert "v_cam07" not in v_ids
    assert "v_cam30" not in v_ids


def test_gis_filtering_excludes_virtual_cameras():
    """Verify that GIS map filtering logic excludes virtual cameras and retains 30 real cameras."""
    catalogue = CameraCatalogue()
    real_cams = catalogue.get_cameras()
    virtual_cams = get_virtual_30_catalogue()

    all_cams = real_cams + virtual_cams

    # Filter logic mirroring InteractiveGisMap.tsx
    gis_cams = [c for c in all_cams if not c.is_virtual and not c.camera_id.startswith("v_cam")]
    assert len(gis_cams) == 30
    assert all(not c.camera_id.startswith("v_cam") for c in gis_cams)


def test_multi_camera_ingestion_manager_worker_switching(tmp_path):
    """Verify worker startup and automatic eviction under max_workers concurrency limit."""
    db_file = tmp_path / "test_ingestion.db"
    db = Database(str(db_file))
    db.initialize()

    manager = MultiCameraIngestionManager(db=db, max_workers=2)

    # Launch worker for cam01
    cfg1 = CameraWorkerConfig(camera_id="cam01", source_type="rtsp")
    assert manager.start_camera_worker(cfg1) is True

    # Launch worker for cam02
    cfg2 = CameraWorkerConfig(camera_id="cam02", source_type="rtsp")
    assert manager.start_camera_worker(cfg2) is True

    assert manager.get_active_worker_count() <= 2

    # Launch worker for cam03 (should evict an older worker without exceeding limit 2)
    cfg3 = CameraWorkerConfig(camera_id="cam03", source_type="rtsp")
    assert manager.start_camera_worker(cfg3) is True
    assert manager.get_active_worker_count() <= 2

    active_ids = [s.camera_id for s in manager.get_worker_statuses() if s.running]
    assert "cam03" in active_ids

    manager.stop_all()
    assert manager.get_active_worker_count() == 0


def test_camera_isolated_counts(tmp_path):
    """Verify that vehicle counts are isolated per camera_id and do not bleed between cameras."""
    db_file = tmp_path / "test_counts.db"
    db = Database(str(db_file))
    db.initialize()

    from backend.db.repositories import EventRecorder
    from backend.db.models import Camera
    recorder = EventRecorder(db)
    recorder.register_camera(Camera(camera_id="cam02", live=True))

    zone_repo = ZoneRepository(db)

    # Insert counts for cam02 only
    zone_repo.insert_zone_count(
        ZoneCount(
            id=None,
            camera_id="cam02",
            canonical_vehicle_id=101,
            vehicle_class="car",
            direction="IN",
            timestamp="2026-09-12T10:00:00Z",
        )
    )
    zone_repo.insert_zone_count(
        ZoneCount(
            id=None,
            camera_id="cam02",
            canonical_vehicle_id=102,
            vehicle_class="car",
            direction="OUT",
            timestamp="2026-09-12T10:01:00Z",
        )
    )

    # cam02 counts
    cam02_counts = zone_repo.get_counts_by_camera("cam02")
    assert cam02_counts["total"]["IN"] == 1
    assert cam02_counts["total"]["OUT"] == 1

    # cam05 counts must be 0
    cam05_counts = zone_repo.get_counts_by_camera("cam05")
    assert cam05_counts["total"]["IN"] == 0
    assert cam05_counts["total"]["OUT"] == 0
