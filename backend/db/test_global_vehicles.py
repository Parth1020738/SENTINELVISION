"""
SentinelVision - Unit Tests for Phase 9.10 Cross-Camera Vehicle Tracking
"""

import pytest
from fastapi.testclient import TestClient

from backend.db.database import Database
from backend.db.repositories import GlobalVehicleRepository, CameraRepository
from backend.db.models import Camera
from backend.api.main import app
from backend.api.deps import Repositories, get_repositories


@pytest.fixture
def db(tmp_path):
    db_file = str(tmp_path / "test_gv.db")
    database = Database(db_file)
    database.initialize()
    # Create test cameras
    cam_repo = CameraRepository(database)
    cam_repo.upsert_camera(Camera(camera_id="cam01", name="Camera 1"))
    cam_repo.upsert_camera(Camera(camera_id="cam05", name="Camera 5"))
    cam_repo.upsert_camera(Camera(camera_id="cam13", name="Camera 13"))
    return database


@pytest.fixture
def repo(db):
    return GlobalVehicleRepository(db)


def test_first_finalized_plate_creates_global_vehicle(repo):
    """1. First finalized plate creates global vehicle."""
    gv = repo.get_or_create_by_plate("GJ 01 AB 1234", vehicle_class="car", timestamp="2026-09-08T10:00:00Z")
    assert gv is not None
    assert gv.global_vehicle_id.startswith("GV-")
    assert gv.normalized_plate == "GJ01AB1234"
    assert gv.vehicle_class == "car"


def test_same_normalized_plate_maps_to_same_global_vehicle(repo):
    """2. Same normalized plate from another camera maps to the same global vehicle."""
    gv1 = repo.get_or_create_by_plate("GJ 01 AB 1234", vehicle_class="car", timestamp="2026-09-08T10:00:00Z")
    gv2 = repo.get_or_create_by_plate("gj-01-ab-1234", vehicle_class="car", timestamp="2026-09-08T10:05:00Z")
    assert gv1.global_vehicle_id == gv2.global_vehicle_id


def test_different_normalized_plate_creates_different_global_vehicle(repo):
    """3. Different normalized plate creates a different global vehicle."""
    gv1 = repo.get_or_create_by_plate("GJ 01 AB 1234", vehicle_class="car")
    gv2 = repo.get_or_create_by_plate("MH 12 XY 9999", vehicle_class="truck")
    assert gv1.global_vehicle_id != gv2.global_vehicle_id


def test_same_canonical_track_does_not_imply_global_identity_by_itself(repo):
    """4. Same camera-local canonical track does not imply global identity by itself."""
    # Observations must be tied to a valid normalized plate signal
    res = repo.get_or_create_by_plate("", vehicle_class="car")
    assert res is None


def test_same_canonical_track_id_different_cameras_not_auto_merged(repo):
    """5. Same canonical track ID on different cameras does NOT automatically merge without matching plate."""
    obs1 = repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=5)
    obs2 = repo.record_plate_observation("MH12XY9999", "cam13", canonical_vehicle_id=5)
    assert obs1.global_vehicle_id != obs2.global_vehicle_id


def test_plate_normalization_applied_before_matching(repo):
    """6. Plate normalization is applied before matching."""
    gv1 = repo.get_or_create_by_plate("HR 99 ABV 2812")
    gv2 = repo.get_or_create_by_plate("hr.99.abv.2812")
    assert gv1.normalized_plate == "HR99ABV2812"
    assert gv1.global_vehicle_id == gv2.global_vehicle_id


def test_conflicting_plates_never_silently_merged(repo):
    """7. Conflicting plates are never silently merged."""
    gv1 = repo.get_or_create_by_plate("GJ01AB1234")
    gv2 = repo.get_or_create_by_plate("GJ05XY9999")
    assert gv1.global_vehicle_id != gv2.global_vehicle_id


def test_multiple_observations_stored(repo):
    """8. Multiple observations are stored."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=10, timestamp="2026-09-08T10:00:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=25, timestamp="2026-09-08T10:05:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam13", canonical_vehicle_id=42, timestamp="2026-09-08T10:12:00Z")

    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    timeline = repo.get_timeline(gv.global_vehicle_id)
    assert len(timeline) == 3


def test_timeline_ordered_by_source_timestamp(repo):
    """9. Timeline is ordered by source timestamp."""
    repo.record_plate_observation("GJ01AB1234", "cam13", canonical_vehicle_id=42, timestamp="2026-09-08T10:20:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=10, timestamp="2026-09-08T10:00:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=25, timestamp="2026-09-08T10:10:00Z")

    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    timeline = repo.get_timeline(gv.global_vehicle_id)
    timestamps = [t.timestamp for t in timeline]
    assert timestamps == sorted(timestamps)


def test_vehicle_class_preserved(repo):
    """10. Vehicle class is preserved."""
    obs = repo.record_plate_observation("DL01AB1234", "cam01", canonical_vehicle_id=1, vehicle_class="bus")
    assert obs.vehicle_class == "bus"
    gv = repo.get_global_vehicle(obs.global_vehicle_id)
    assert gv.vehicle_class == "bus"


def test_unknown_unresolved_observations_no_fabricated_ids(repo):
    """11. Unknown/unresolved observations do not receive fabricated global IDs."""
    obs = repo.record_plate_observation("", "cam01", canonical_vehicle_id=1)
    assert obs is None
    obs2 = repo.record_plate_observation(None, "cam01", canonical_vehicle_id=1)
    assert obs2 is None


def test_api_list_works(db):
    """12. API list works."""
    repo = GlobalVehicleRepository(db)
    repo.get_or_create_by_plate("GJ01AB1234", vehicle_class="car")
    repo.get_or_create_by_plate("MH12XY9999", vehicle_class="truck")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get("/api/vehicles")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 2
    app.dependency_overrides.clear()


def test_api_detail_works(db):
    """13. API detail works."""
    repo = GlobalVehicleRepository(db)
    gv = repo.get_or_create_by_plate("DL01AB1234", vehicle_class="car")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get(f"/api/vehicles/{gv.global_vehicle_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["global_vehicle_id"] == gv.global_vehicle_id
    assert data["normalized_plate"] == "DL01AB1234"
    app.dependency_overrides.clear()


def test_api_timeline_works(db):
    """14. Timeline API works."""
    repo = GlobalVehicleRepository(db)
    obs1 = repo.record_plate_observation("KA05M9999", "cam01", canonical_vehicle_id=1, timestamp="2026-09-08T10:00:00Z")
    obs2 = repo.record_plate_observation("KA05M9999", "cam05", canonical_vehicle_id=2, timestamp="2026-09-08T10:10:00Z")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get(f"/api/vehicles/{obs1.global_vehicle_id}/timeline")
    assert res.status_code == 200
    data = res.json()
    assert data["observation_count"] == 2
    assert len(data["timeline"]) == 2
    assert data["timeline"][0]["camera_id"] == "cam01"
    assert data["timeline"][1]["camera_id"] == "cam05"
    app.dependency_overrides.clear()


def test_plate_search_works(db):
    """15. Plate search works."""
    repo = GlobalVehicleRepository(db)
    gv = repo.get_or_create_by_plate("TN07CB1234", vehicle_class="car")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get("/api/vehicles/search?plate=tn-07-cb-1234")
    assert res.status_code == 200
    data = res.json()
    assert data["global_vehicle_id"] == gv.global_vehicle_id
    assert data["normalized_plate"] == "TN07CB1234"
    app.dependency_overrides.clear()
