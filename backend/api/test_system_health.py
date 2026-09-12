"""
SentinelVision - System Health API Tests

Phase 9.12: Integration tests for /api/system/health and /api/cameras/health endpoints,
summary count invariants, attention separation, and credential protection.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.deps import Repositories, get_repositories, reset_repositories
from backend.db.database import Database
from backend.db.models import CameraHealth


@pytest.fixture
def test_repositories(tmp_path):
    from backend.ai.multi_ingestion import global_ingestion_manager
    global_ingestion_manager.stop_all()
    reset_repositories()
    db_file = str(tmp_path / "test_api_health.db")
    db = Database(db_file)
    db.initialize()
    repos = Repositories.from_database(db)

    # Seed some runtime health records
    repos.health.upsert_health(CameraHealth(camera_id="cam01", status="ONLINE", last_successful_frame_at="2026-09-08T10:00:00Z"))
    repos.health.upsert_health(CameraHealth(camera_id="cam02", status="DEGRADED", reconnect_count=3, last_error="Intermittent frame drop"))
    repos.health.upsert_health(CameraHealth(camera_id="cam03", status="OFFLINE", consecutive_failures=60, last_error="Connection rejected"))

    def override_get_repositories():
        return repos

    app.dependency_overrides[get_repositories] = override_get_repositories
    yield repos
    app.dependency_overrides.clear()
    reset_repositories()


def test_system_health_endpoint(test_repositories):
    client = TestClient(app)
    response = client.get("/api/system/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "summary font" not in data  # schema check
    summary = data["summary"]

    total = summary["total_configured"]
    online = summary["online_count"]
    degraded = summary["degraded_count"]
    offline = summary["offline_count"]
    not_checked = summary["not_checked_count"]

    # Invariant Check: online + degraded + offline + not_checked == total_configured
    assert online + degraded + offline + not_checked == total
    assert total == 30
    assert online == 1
    assert degraded == 1
    assert offline == 1
    assert not_checked == 27
    assert summary["ai_active_count"] == 1

    cameras = data["cameras"]
    assert len(cameras) == 30

    # Ensure cam01 is ONLINE and AI ACTIVE
    cam1 = next(c for c in cameras if c["camera_id"] == "cam01")
    assert cam1["status"] == "ONLINE"
    assert cam1["ai_active"] is True

    # Ensure cam02 is DEGRADED
    cam2 = next(c for c in cameras if c["camera_id"] == "cam02")
    assert cam2["status"] == "DEGRADED"
    assert cam2["reconnect_count"] == 3

    # Ensure cam04 is NOT_CHECKED
    cam4 = next(c for c in cameras if c["camera_id"] == "cam04")
    assert cam4["status"] == "NOT_CHECKED"


def test_cameras_health_endpoint(test_repositories):
    client = TestClient(app)
    response = client.get("/api/cameras/health")
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) == 30


def test_credential_security_in_health_response(test_repositories):
    client = TestClient(app)
    res1 = client.get("/api/system/health")
    res2 = client.get("/api/cameras/health")
    
    text1 = res1.text.lower()
    text2 = res2.text.lower()

    # Verify no RTSP credentials or secrets appear in payloads
    for s in ["rtsp://", "password", "secret", "userinfo"]:
        assert s not in text1
        assert s not in text2
