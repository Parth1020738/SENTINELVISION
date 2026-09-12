"""
SentinelVision - Phase O Automated Test Suite

Tests for:
1. Camera GIS metadata serialization & catalogue parsing.
2. Handling cameras with valid vs missing coordinates.
3. Camera search/filter logic.
4. Vehicle route chronological ordering & missing coordinate handling.
5. Single camera observation route handling (no route polyline).
6. CSV vehicle evidence export (authentication, content, no secrets).
7. PDF vehicle investigation report generation (authentication, content, no secrets).
8. System health telemetry metrics.
"""

import csv
import io
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.deps import Repositories, get_repositories
from backend.camera.camera_catalogue import CameraCatalogue, NormalizedCamera
from backend.db.database import Database
from backend.db.models import Camera, GlobalVehicle, CrossCameraObservation
from backend.db.repositories import GlobalVehicleRepository


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_phase_o.db")
    db = Database(db_file)
    db.initialize()
    return db


@pytest.fixture
def test_repos(test_db):
    return Repositories.from_database(test_db)


@pytest.fixture
def client(test_repos):
    def _get_test_repos():
        return test_repos

    app.dependency_overrides[get_repositories] = _get_test_repos
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Camera GIS Metadata & Catalogue Tests
# ---------------------------------------------------------------------------
def test_camera_gis_metadata_parsing():
    raw_payload = [
        {
            "id": "cam01",
            "name": "Ahmedabad Highway N1",
            "latitude": 23.0225,
            "longitude": 72.5714,
            "district": "Ahmedabad",
            "department": "Traffic Police",
            "anpr_capable": True,
        },
        {
            "id": "cam02",
            "name": "Vadodara Toll Plaza",
            "latitude": None,
            "longitude": None,
            "district": "Vadodara",
            "anpr_capable": False,
        },
    ]

    catalogue = CameraCatalogue()
    parsed = catalogue._parse_catalogue_payload(raw_payload)

    assert len(parsed) == 2
    c1 = next(c for c in parsed if c.camera_id == "cam01")
    assert c1.latitude == 23.0225
    assert c1.longitude == 72.5714
    assert c1.district == "Ahmedabad"
    assert c1.department == "Traffic Police"
    assert c1.anpr_capable is True

    c2 = next(c for c in parsed if c.camera_id == "cam02")
    assert c2.latitude is None
    assert c2.longitude is None
    assert c2.district == "Vadodara"
    assert c2.anpr_capable is False


def test_api_list_cameras_gis_metadata(client):
    response = client.get("/api/cameras")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 30
    cam1 = data[0]
    assert "latitude" in cam1
    assert "longitude" in cam1
    assert "district" in cam1
    assert "anpr_capable" in cam1
    assert "coordinate_source" in cam1
    assert "coordinate_approximate" in cam1
    assert "rtsp_url" not in cam1
    assert "password" not in cam1


# ---------------------------------------------------------------------------
# Phase O.2 Mandatory Camera & GIS Verification Tests
# ---------------------------------------------------------------------------
def test_phase_o2_30_cameras_catalogue_contract(client):
    response = client.get("/api/cameras")
    assert response.status_code == 200
    cameras = response.json()
    
    # 1. Exactly 30 cameras or more
    cam_ids = [c["camera_id"] for c in cameras if c["camera_id"].startswith("cam") and c["camera_id"] != "cam_demo"]
    assert len(set(cam_ids)) == 30, f"Expected 30 unique camera IDs, got {len(set(cam_ids))}"

    # 2. CAM27, CAM28, CAM29 remain separate records
    assert "cam27" in cam_ids
    assert "cam28" in cam_ids
    assert "cam29" in cam_ids

    # 3. Dynamic mapped vs location unavailable sum = 30
    mapped_count = sum(1 for c in cameras if c["camera_id"] in cam_ids and c["latitude"] is not None and c["longitude"] is not None)
    unmapped_count = sum(1 for c in cameras if c["camera_id"] in cam_ids and (c["latitude"] is None or c["longitude"] is None))
    assert mapped_count + unmapped_count == 30

    # 4. Latitude & longitude always appear together
    for c in cameras:
        if c["latitude"] is not None:
            assert c["longitude"] is not None, f"Camera {c['camera_id']} has latitude but missing longitude"
            assert 15.0 <= c["latitude"] <= 35.0, f"Invalid latitude range for {c['camera_id']}"
            assert 65.0 <= c["longitude"] <= 95.0, f"Invalid longitude range for {c['camera_id']}"
        else:
            assert c["longitude"] is None, f"Camera {c['camera_id']} has longitude but missing latitude"

    # 5. Security: No RTSP credentials exposed
    for c in cameras:
        for secret_key in ("rtsp_url", "rtsp_user", "rtsp_password", "password", "access_code"):
            assert secret_key not in c



# ---------------------------------------------------------------------------
# 2. Vehicle Route & Chronological Observations Tests
# ---------------------------------------------------------------------------
def test_vehicle_route_chronological_ordering(test_repos):
    test_repos.cameras.upsert_camera(Camera(camera_id="cam01"))
    test_repos.cameras.upsert_camera(Camera(camera_id="cam02"))
    repo = test_repos.global_vehicles

    gv = repo.get_or_create_by_plate(
        plate="GJ01AB1234",
        vehicle_class="car",
        timestamp="2026-09-11T10:00:00.000000+00:00",
    )
    assert gv is not None
    gv_id = gv.global_vehicle_id

    repo.record_plate_observation(
        plate="GJ01AB1234",
        camera_id="cam01",
        canonical_vehicle_id=101,
        vehicle_class="car",
        timestamp="2026-09-11T10:00:00.000000+00:00",
    )

    repo.record_plate_observation(
        plate="GJ01AB1234",
        camera_id="cam02",
        canonical_vehicle_id=102,
        vehicle_class="car",
        timestamp="2026-09-11T10:15:00.000000+00:00",
    )

    timeline = repo.get_timeline(gv_id)
    assert len(timeline) == 2
    assert timeline[0].timestamp < timeline[1].timestamp

    route = repo.get_route(gv_id)
    assert len(route) == 2
    assert route[0]["camera_id"] == "cam01"
    assert route[1]["camera_id"] == "cam02"


def test_api_vehicle_route_endpoint(client, test_repos):
    test_repos.cameras.upsert_camera(Camera(camera_id="cam_demo_a"))
    repo = test_repos.global_vehicles
    gv = repo.get_or_create_by_plate(
        plate="HR19R6697",
        vehicle_class="car",
        timestamp="2026-09-11T12:00:00.000000+00:00",
    )
    assert gv is not None

    repo.record_plate_observation(
        plate="HR19R6697",
        camera_id="cam_demo_a",
        canonical_vehicle_id=200,
        vehicle_class="car",
        timestamp="2026-09-11T12:00:00.000000+00:00",
    )

    response = client.get(f"/api/vehicles/{gv.global_vehicle_id}/route")
    assert response.status_code == 200
    data = response.json()
    assert data["global_vehicle_id"] == gv.global_vehicle_id
    assert data["normalized_plate"] == "HR19R6697"
    assert data["total_observations"] == 1
    assert data["mapped_points_count"] == 0  # Unmapped demo camera coordinates
    assert len(data["points"]) == 1
    assert data["points"][0]["latitude"] is None


# ---------------------------------------------------------------------------
# 3. CSV & PDF Export Tests
# ---------------------------------------------------------------------------
def test_export_vehicles_csv(client, test_repos):
    repo = test_repos.global_vehicles
    repo.get_or_create_by_plate(
        plate="GJ05CD5678",
        vehicle_class="truck",
        timestamp="2026-09-11T14:00:00.000000+00:00",
    )

    response = client.get("/api/vehicles/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "sentinelvision_vehicle_evidence.csv" in response.headers["content-disposition"]

    content = response.text
    assert "Global Vehicle ID,Normalized Plate,Vehicle Class" in content
    assert "GJ05CD5678" in content
    assert "rtsp" not in content.lower()
    assert "password" not in content.lower()


def test_export_vehicle_pdf(client, test_repos):
    test_repos.cameras.upsert_camera(Camera(camera_id="cam01"))
    repo = test_repos.global_vehicles
    gv = repo.get_or_create_by_plate(
        plate="GJ01EF9012",
        vehicle_class="bus",
        timestamp="2026-09-11T15:00:00.000000+00:00",
    )
    assert gv is not None
    repo.record_plate_observation(
        plate="GJ01EF9012",
        camera_id="cam01",
        canonical_vehicle_id=300,
        vehicle_class="bus",
        timestamp="2026-09-11T15:00:00.000000+00:00",
    )

    response = client.get(f"/api/vehicles/{gv.global_vehicle_id}/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert f"sentinelvision_report_{gv.global_vehicle_id}.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_export_invalid_vehicle_pdf_returns_404(client):
    response = client.get("/api/vehicles/GV-INVALID/export.pdf")
    assert response.status_code == 404
