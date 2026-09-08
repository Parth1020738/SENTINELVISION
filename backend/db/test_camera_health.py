"""
SentinelVision - Camera Health Repository Tests

Phase 9.12: Unit tests for camera runtime health persistence, status transitions,
reconnect counters, failure tracking, and summary count invariants.
"""

import pytest

from backend.db.database import Database
from backend.db.models import CameraHealth
from backend.db.repositories import CameraHealthRepository, CameraRepository


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_health.db")
    db = Database(db_file)
    db.initialize()
    return db


def test_camera_health_initial_not_checked(test_db):
    repo = CameraHealthRepository(test_db)
    health = repo.get_health("cam01")
    assert health is None


def test_camera_health_record_success(test_db):
    repo = CameraHealthRepository(test_db)
    h = repo.record_success("cam01", timestamp="2026-09-08T10:00:00Z")
    assert h.camera_id == "cam01"
    assert h.status == "ONLINE"
    assert h.last_successful_frame_at == "2026-09-08T10:00:00Z"
    assert h.consecutive_failures == 0
    assert h.reconnect_count == 0


def test_camera_health_record_failure_transitions(test_db):
    repo = CameraHealthRepository(test_db)
    
    # First failure -> DEGRADED
    h1 = repo.record_failure("cam02", error_msg="rtsp://secret_user:secret_pass@103.250.160.189:8554/stream/cam02", timestamp="2026-09-08T10:01:00Z")
    assert h1.status == "DEGRADED"
    assert h1.consecutive_failures == 1
    # Check error is sanitized (no credentials)
    assert "secret_user" not in h1.last_error
    assert "secret_pass" not in h1.last_error

    # Sustained failures (60+) -> OFFLINE
    h2 = repo.record_failure("cam02", error_msg="Stream unreadable", consecutive=60)
    assert h2.status == "OFFLINE"
    assert h2.consecutive_failures == 60


def test_camera_health_record_reconnect(test_db):
    repo = CameraHealthRepository(test_db)
    repo.record_success("cam03")
    
    h1 = repo.record_reconnect("cam03")
    assert h1.status == "DEGRADED"
    assert h1.reconnect_count == 1

    h2 = repo.record_reconnect("cam03")
    assert h2.reconnect_count == 2
    assert h2.status == "DEGRADED"


def test_camera_health_list_and_upsert(test_db):
    repo = CameraHealthRepository(test_db)
    repo.upsert_health(CameraHealth(camera_id="cam01", status="ONLINE", last_successful_frame_at="2026-09-08T10:00:00Z"))
    repo.upsert_health(CameraHealth(camera_id="cam02", status="DEGRADED", reconnect_count=2))
    repo.upsert_health(CameraHealth(camera_id="cam03", status="OFFLINE", consecutive_failures=60))

    all_h = repo.list_health()
    assert len(all_h) == 3
    statuses = {h.camera_id: h.status for h in all_h}
    assert statuses == {"cam01": "ONLINE", "cam02": "DEGRADED", "cam03": "OFFLINE"}
