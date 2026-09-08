"""
SentinelVision - Unit Tests for Phase 9.11 GIS Route / Vehicle Movement Map
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
    db_file = str(tmp_path / "test_gis_route.db")
    database = Database(db_file)
    database.initialize()
    cam_repo = CameraRepository(database)
    # Camera with valid coordinates
    cam_repo.upsert_camera(Camera(camera_id="cam01", name="Camera 1", latitude=23.2156, longitude=72.6369))
    # Camera without coordinates (location null)
    cam_repo.upsert_camera(Camera(camera_id="cam05", name="Camera 5", latitude=None, longitude=None))
    # Camera with valid coordinates
    cam_repo.upsert_camera(Camera(camera_id="cam13", name="Camera 13", latitude=23.2500, longitude=72.6800))
    return database


@pytest.fixture
def repo(db):
    return GlobalVehicleRepository(db)


def test_route_endpoint_returns_vehicle_route(db, repo):
    """1. Route endpoint returns vehicle route."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=1, timestamp="2026-09-08T10:00:00Z")
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get(f"/api/vehicles/{gv.global_vehicle_id}/route")
    assert res.status_code == 200
    data = res.json()
    assert data["global_vehicle_id"] == gv.global_vehicle_id
    assert len(data["points"]) == 1
    app.dependency_overrides.clear()


def test_route_points_ordered_by_source_timestamp_ascending(repo):
    """2. Route points are ordered by source timestamp ascending."""
    repo.record_plate_observation("GJ01AB1234", "cam13", canonical_vehicle_id=40, timestamp="2026-09-08T10:30:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=10, timestamp="2026-09-08T10:10:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=25, timestamp="2026-09-08T10:20:00Z")

    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    timestamps = [p["timestamp"] for p in points]
    assert timestamps == sorted(timestamps)
    assert points[0]["camera_id"] == "cam01"
    assert points[1]["camera_id"] == "cam05"
    assert points[2]["camera_id"] == "cam13"


def test_camera_coordinates_attached_correctly(repo):
    """3. Camera coordinates are attached correctly when available."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=1, timestamp="2026-09-08T10:00:00Z")
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["latitude"] == 23.2156
    assert points[0]["longitude"] == 72.6369


def test_same_camera_observation_retains_correct_camera_id(repo):
    """4. Same camera observation retains correct camera ID."""
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=2, timestamp="2026-09-08T10:00:00Z")
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["camera_id"] == "cam05"


def test_vehicle_class_preserved(repo):
    """5. Vehicle class is preserved."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=1, vehicle_class="bus")
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["vehicle_class"] == "bus"


def test_canonical_vehicle_id_preserved(repo):
    """6. Canonical vehicle ID is preserved."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=99)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["canonical_vehicle_id"] == 99


def test_normalized_plate_preserved(repo):
    """7. Normalized plate is preserved."""
    repo.record_plate_observation("gj-01-ab-1234", "cam01", canonical_vehicle_id=1)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["normalized_plate"] == "GJ01AB1234"


def test_null_coordinates_handled_correctly(repo):
    """8. Null coordinates are handled correctly."""
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=1)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["latitude"] is None
    assert points[0]["longitude"] is None


def test_unknown_camera_location_does_not_crash_route_generation(db, repo):
    """9. Unknown camera location does not crash route generation."""
    cam_repo = CameraRepository(db)
    cam_repo.upsert_camera(Camera(camera_id="cam999", name="Unmapped Camera", latitude=None, longitude=None))
    repo.record_plate_observation("GJ01AB1234", "cam999", canonical_vehicle_id=1)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert len(points) == 1
    assert points[0]["camera_id"] == "cam999"
    assert points[0]["latitude"] is None
    assert points[0]["longitude"] is None


def test_unknown_camera_location_does_not_receive_fabricated_coordinates(db, repo):
    """10. Unknown camera location does not receive fabricated coordinates."""
    cam_repo = CameraRepository(db)
    cam_repo.upsert_camera(Camera(camera_id="cam999", name="Unmapped Camera", latitude=None, longitude=None))
    repo.record_plate_observation("GJ01AB1234", "cam999", canonical_vehicle_id=1)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    points = repo.get_route(gv.global_vehicle_id)
    assert points[0]["latitude"] is None
    assert points[0]["longitude"] is None


def test_zero_coordinate_observations_mapped_count(db, repo):
    """11. Zero coordinate observations produce 0 mapped points."""
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=1)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get(f"/api/vehicles/{gv.global_vehicle_id}/route")
    assert res.status_code == 200
    data = res.json()
    assert data["total_observations"] == 1
    assert data["mapped_points_count"] == 0
    app.dependency_overrides.clear()


def test_one_coordinate_observation_mapped_count(db, repo):
    """12. One coordinate observation produces 1 mapped point."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=1)
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get(f"/api/vehicles/{gv.global_vehicle_id}/route")
    assert res.status_code == 200
    data = res.json()
    assert data["total_observations"] == 1
    assert data["mapped_points_count"] == 1
    app.dependency_overrides.clear()


def test_two_or_more_coordinates_produce_ordered_route_points(db, repo):
    """13. Two or more coordinates produce ordered route points."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=1, timestamp="2026-09-08T10:00:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam13", canonical_vehicle_id=2, timestamp="2026-09-08T10:10:00Z")
    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")

    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get(f"/api/vehicles/{gv.global_vehicle_id}/route")
    assert res.status_code == 200
    data = res.json()
    assert data["total_observations"] == 2
    assert data["mapped_points_count"] == 2
    assert data["points"][0]["camera_id"] == "cam01"
    assert data["points"][1]["camera_id"] == "cam13"
    app.dependency_overrides.clear()


def test_timeline_remains_intact_when_coordinates_missing(repo):
    """14. Timeline remains intact when coordinates are missing."""
    repo.record_plate_observation("GJ01AB1234", "cam01", canonical_vehicle_id=1, timestamp="2026-09-08T10:00:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam05", canonical_vehicle_id=2, timestamp="2026-09-08T10:05:00Z")
    repo.record_plate_observation("GJ01AB1234", "cam13", canonical_vehicle_id=3, timestamp="2026-09-08T10:10:00Z")

    gv = repo.get_global_vehicle_by_plate("GJ01AB1234")
    timeline = repo.get_timeline(gv.global_vehicle_id)
    assert len(timeline) == 3


def test_nonexistent_global_vehicle_route_returns_404(db):
    """15. Nonexistent global vehicle returns 404 error."""
    app.dependency_overrides[get_repositories] = lambda: Repositories.from_database(db)
    client = TestClient(app)
    res = client.get("/api/vehicles/GV-999999/route")
    assert res.status_code == 404
    app.dependency_overrides.clear()
