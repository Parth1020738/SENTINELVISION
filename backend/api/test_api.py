"""
SentinelVision - API Tests

Phase 6C: Tests for the FastAPI backend API.

Uses a temporary SQLite database (no RTSP / GPU / YOLO / camera grid /
internet / real credentials).  The production ``get_repositories``
dependency is overridden with a test database, so no test ever touches
``data/sentinelvision.db``.

Run:  python -m backend.api.test_api -v
"""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api import deps
from backend.api.deps import Repositories
from backend.api.main import app
from backend.api.schemas import (
    CameraResponse,
    CountsResponse,
    DirectionTotals,
    PlateReadResponse,
    PlateSearchResponse,
    VehicleEventResponse,
)
from backend.ai.plate_ocr import normalize_plate_text
from backend.db.database import Database
from backend.db.models import Alert, Camera, PlateRead, VehicleEvent, ZoneCount


class APITestCase(unittest.TestCase):
    """Shared fixture: temp database + TestClient with override."""

    def setUp(self):
        from backend.camera.camera_catalogue import global_catalogue
        global_catalogue.fetcher = lambda url, t: None
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._tmpdir.name, "test.db"))
        self.db.initialize()
        self.repos = Repositories.from_database(self.db)
        app.dependency_overrides[deps.get_repositories] = lambda: self.repos
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(deps.get_repositories, None)
        self._tmpdir.cleanup()

    # -- data helpers ---------------------------------------------------
    def add_camera(self, camera_id="cam01", **kwargs):
        camera = Camera(
            camera_id=camera_id,
            name=kwargs.get("name", f"Camera {camera_id}"),
            location=kwargs.get("location", "Gate 1"),
            latitude=kwargs.get("latitude", 28.61),
            longitude=kwargs.get("longitude", 77.21),
            codec=kwargs.get("codec", "h264"),
            width=kwargs.get("width", 1920),
            height=kwargs.get("height", 1080),
            rtsp_url=kwargs.get(
                "rtsp_url",
                f"rtsp://user:secret123@192.168.1.50:554/stream/{camera_id}",
            ),
            live=kwargs.get("live", True),
        )
        self.repos.cameras.upsert_camera(camera)
        return camera

    def add_event(self, vehicle=1, camera_id="cam01", **kwargs):
        if self.repos.cameras.get_camera(camera_id) is None:
            self.add_camera(camera_id)
        event = VehicleEvent(
            canonical_vehicle_id=vehicle,
            camera_id=camera_id,
            vehicle_class=kwargs.get("vehicle_class", "car"),
            event_type=kwargs.get("event_type", "DETECTED"),
            timestamp=kwargs.get("timestamp", "2026-01-01T00:00:00+00:00"),
            confidence=kwargs.get("confidence", 0.9),
            direction=kwargs.get("direction"),
        )
        self.repos.vehicles.insert_vehicle_event(event)
        return event

    def add_plate(self, vehicle=1, camera_id="cam01", **kwargs):
        if self.repos.cameras.get_camera(camera_id) is None:
            self.add_camera(camera_id)
        read = PlateRead(
            canonical_vehicle_id=vehicle,
            camera_id=camera_id,
            raw_ocr=kwargs.get("raw_ocr", "HR99ABV2812"),
            normalized_plate=kwargs.get("normalized_plate", "HR99ABV2812"),
            timestamp=kwargs.get("timestamp", "2026-01-01T00:00:00+00:00"),
            ocr_confidence=0.9,
            combined_confidence=0.85,
        )
        self.repos.plates.insert_plate_read(read)
        return read

    def add_count(self, vehicle=1, camera_id="cam01", **kwargs):
        if self.repos.cameras.get_camera(camera_id) is None:
            self.add_camera(camera_id)
        count = ZoneCount(
            camera_id=camera_id,
            canonical_vehicle_id=vehicle,
            vehicle_class=kwargs.get("vehicle_class", "car"),
            direction=kwargs.get("direction", "IN"),
            timestamp=kwargs.get("timestamp", "2026-01-01T00:00:00+00:00"),
        )
        self.repos.zones.insert_zone_count(count)
        return count


# ---------------------------------------------------------------------------
# 1. App imports / wiring
# ---------------------------------------------------------------------------
class TestAppImport(APITestCase):
    def test_app_importable(self):
        from backend.api import app as exported_app
        from backend.api.main import app as main_app

        self.assertIs(exported_app, main_app)

    def test_app_metadata(self):
        self.assertEqual(app.title, "SentinelVision API")
        self.assertEqual(app.version, "1.0.0")


# ---------------------------------------------------------------------------
# 2. Health
# ---------------------------------------------------------------------------
class TestHealth(APITestCase):
    def test_health_ok(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "ok")



# ---------------------------------------------------------------------------
# 3-6. Cameras
# ---------------------------------------------------------------------------
class TestCameras(APITestCase):
    def test_empty_cameras(self):
        res = self.client.get("/api/cameras")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_camera_listing(self):
        self.add_camera("cam01")
        self.add_camera("cam02")
        res = self.client.get("/api/cameras")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body), 2)
        self.assertEqual([c["camera_id"] for c in body], ["cam01", "cam02"])

    def test_camera_lookup(self):
        self.add_camera("cam01")
        res = self.client.get("/api/cameras/cam01")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["camera_id"], "cam01")
        self.assertEqual(body["codec"], "h264")
        self.assertEqual(body["width"], 1920)
        self.assertEqual(body["height"], 1080)
        self.assertTrue(body["live"])

    def test_missing_camera_404(self):
        res = self.client.get("/api/cameras/nope")
        self.assertEqual(res.status_code, 404)
        self.assertIn("detail", res.json())

    def test_no_credentials_in_camera_response(self):
        self.add_camera("cam01")
        text = self.client.get("/api/cameras/cam01").text
        self.assertNotIn("secret123", text)
        self.assertNotIn("rtsp://", text)
        self.assertNotIn("rtsp_url", text)
        self.assertNotIn("webrtc_url", text)
        self.assertNotIn("hls_url", text)

    def test_no_authenticated_rtsp_url_in_listing(self):
        self.add_camera("cam01")
        self.add_camera("cam02")
        text = self.client.get("/api/cameras").text
        self.assertNotIn("user:secret123@", text)
        self.assertNotIn("secret123", text)


# ---------------------------------------------------------------------------
# 7-8. Vehicle history
# ---------------------------------------------------------------------------
class TestVehicleHistory(APITestCase):
    def test_vehicle_history(self):
        self.add_event(vehicle=7, event_type="DETECTED")
        self.add_event(vehicle=7, event_type="ZONE_IN")
        self.add_event(vehicle=8, event_type="DETECTED")
        body = self.client.get("/api/vehicles/7/history").json()
        self.assertEqual(len(body), 2)
        self.assertTrue(all(e["canonical_vehicle_id"] == 7 for e in body))

    def test_empty_vehicle_history(self):
        res = self.client.get("/api/vehicles/999/history")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_vehicle_history_schema_shape(self):
        self.add_event(vehicle=3)
        body = self.client.get("/api/vehicles/3/history").json()[0]
        for key in (
            "canonical_vehicle_id",
            "camera_id",
            "vehicle_class",
            "event_type",
            "timestamp",
        ):
            self.assertIn(key, body)



# ---------------------------------------------------------------------------
# 9-12. Plate search
# ---------------------------------------------------------------------------
class TestPlateSearch(APITestCase):
    def test_exact_plate_search(self):
        self.add_plate(vehicle=1)
        body = self.client.get(
            "/api/plates/search", params={"plate": "HR99ABV2812"}
        ).json()
        self.assertEqual(body["match"], "exact")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["normalized_plate"], "HR99ABV2812")

    def test_normalized_plate_search(self):
        self.add_plate(vehicle=1)
        body = self.client.get(
            "/api/plates/search", params={"plate": "HR 99 ABV2812"}
        ).json()
        self.assertEqual(body["normalized_query"], "HR99ABV2812")
        self.assertEqual(body["count"], 1)

    def test_partial_plate_search(self):
        self.add_plate(vehicle=1)
        body = self.client.get(
            "/api/plates/search",
            params={"plate": "ABV2812", "match": "partial"},
        ).json()
        self.assertEqual(body["match"], "partial")
        self.assertEqual(body["count"], 1)

    def test_empty_plate_search(self):
        body = self.client.get(
            "/api/plates/search", params={"plate": "ZZ00ZZZ000"}
        ).json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_plate_search_response_fields(self):
        self.add_plate(vehicle=5)
        body = self.client.get(
            "/api/plates/search", params={"plate": "HR99ABV2812"}
        ).json()
        for key in ("query", "normalized_query", "match", "count", "results"):
            self.assertIn(key, body)



# ---------------------------------------------------------------------------
# 13-16. Counts
# ---------------------------------------------------------------------------
class TestCounts(APITestCase):
    def setUp(self):
        super().setUp()
        self.add_count(vehicle=1, camera_id="cam01", vehicle_class="car", direction="IN")
        self.add_count(vehicle=2, camera_id="cam01", vehicle_class="car", direction="OUT")
        self.add_count(vehicle=3, camera_id="cam01", vehicle_class="truck", direction="IN")
        self.add_count(vehicle=4, camera_id="cam02", vehicle_class="car", direction="IN")

    def test_counts_all(self):
        body = self.client.get("/api/counts").json()
        self.assertEqual(body["total"], {"IN": 3, "OUT": 1})
        self.assertIn("car", body["by_class"])
        self.assertIn("truck", body["by_class"])

    def test_counts_by_camera(self):
        body = self.client.get("/api/counts", params={"camera_id": "cam01"}).json()
        self.assertEqual(body["filters"]["camera_id"], "cam01")
        self.assertEqual(body["total"], {"IN": 2, "OUT": 1})

    def test_counts_by_class(self):
        body = self.client.get(
            "/api/counts", params={"vehicle_class": "truck"}
        ).json()
        self.assertEqual(body["total"], {"IN": 1, "OUT": 0})

    def test_counts_by_direction(self):
        body = self.client.get("/api/counts", params={"direction": "OUT"}).json()
        self.assertEqual(body["total"], {"IN": 0, "OUT": 1})

    def test_counts_by_camera_and_direction(self):
        body = self.client.get(
            "/api/counts",
            params={"camera_id": "cam02", "direction": "IN"},
        ).json()
        self.assertEqual(body["total"], {"IN": 1, "OUT": 0})

    def test_counts_empty_database(self):
        body = self.client.get("/api/counts", params={"camera_id": "cam03"}).json()
        self.assertEqual(body["total"], {"IN": 0, "OUT": 0})
        self.assertEqual(body["by_class"], {})

    def test_counts_invalid_direction_rejected(self):
        res = self.client.get("/api/counts", params={"direction": "SIDEWAYS"})
        self.assertEqual(res.status_code, 422)



# ---------------------------------------------------------------------------
# 17-18. Errors / schema validation / security
# ---------------------------------------------------------------------------
class TestErrorsAndSchemas(APITestCase):
    def test_invalid_plate_query_missing(self):
        res = self.client.get("/api/plates/search")
        self.assertEqual(res.status_code, 422)

    def test_invalid_match_mode_rejected(self):
        res = self.client.get(
            "/api/plates/search", params={"plate": "HR99ABV2812", "match": "fuzzy"}
        )
        self.assertEqual(res.status_code, 422)

    def test_invalid_vehicle_id_rejected(self):
        res = self.client.get("/api/vehicles/notanumber/history")
        self.assertEqual(res.status_code, 422)

    def test_schema_models_validate_camera(self):
        schema = CameraResponse(
            camera_id="cam01", name="N", codec="h264", width=1920, height=1080
        )
        data = schema.model_dump()
        self.assertEqual(data["camera_id"], "cam01")
        self.assertFalse(data["live"])

    def test_schema_models_validate_event_plate_counts(self):
        event = VehicleEventResponse(
            canonical_vehicle_id=1, camera_id="c", vehicle_class="car",
            event_type="DETECTED",
        )
        plate = PlateReadResponse(canonical_vehicle_id=1, camera_id="c", raw_ocr="X")
        counts = CountsResponse(
            filters={}, total=DirectionTotals(IN=1, OUT=0), by_class={}
        )
        self.assertEqual(event.canonical_vehicle_id, 1)
        self.assertEqual(plate.raw_ocr, "X")
        self.assertEqual(counts.total.IN, 1)

    def test_plate_search_response_schema_roundtrip(self):
        self.add_plate(vehicle=9)
        body = self.client.get(
            "/api/plates/search", params={"plate": "HR99ABV2812"}
        ).json()
        parsed = PlateSearchResponse(**body)
        self.assertEqual(parsed.count, 1)

    def test_no_credentials_in_any_response(self):
        self.add_camera("cam01")
        self.add_event(vehicle=1)
        self.add_plate(vehicle=1)
        self.add_count(vehicle=1)
        for url in (
            "/health",
            "/api/cameras",
            "/api/cameras/cam01",
            "/api/vehicles/1/history",
            "/api/plates/search?plate=HR99ABV2812",
            "/api/counts",
        ):
            text = self.client.get(url).text
            self.assertNotIn("secret123", text, url)
            self.assertNotIn("SENTINEL_RTSP_EMAIL", text, url)
            self.assertNotIn("SENTINEL_RTSP_PASSWORD", text, url)


# ---------------------------------------------------------------------------
# Phase 7: Watchlist endpoints
# ---------------------------------------------------------------------------
class TestWatchlistAPI(APITestCase):
    def add_watch(self, plate="GJ01AB1234", **kw):
        return self.client.post(
            "/api/watchlist",
            json={
                "plate": kw.get("plate", plate),
                "reason": kw.get("reason", "Reported stolen vehicle"),
                "category": kw.get("category", "STOLEN"),
                "priority": kw.get("priority", "HIGH"),
                "notes": kw.get("notes"),
            },
        )

    def test_get_empty_watchlist(self):
        res = self.client.get("/api/watchlist")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 0)
        self.assertEqual(res.json()["results"], [])

    def test_post_watchlist(self):
        res = self.add_watch()
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["normalized_plate"], "GJ01AB1234")
        self.assertEqual(body["reason"], "Reported stolen vehicle")
        self.assertEqual(body["category"], "STOLEN")
        self.assertEqual(body["priority"], "HIGH")
        self.assertTrue(body["active"])

    def test_post_watchlist_normalized(self):
        res = self.add_watch(plate="GJ 01 AB 1234")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["normalized_plate"], "GJ01AB1234")

    def test_post_missing_reason_rejected(self):
        # Missing reason -> Pydantic required-field validation (422).
        res = self.client.post("/api/watchlist", json={"plate": "GJ01AB1234"})
        self.assertEqual(res.status_code, 422)
        # Present-but-blank reason -> route-level validation (400).
        res = self.client.post(
            "/api/watchlist", json={"plate": "GJ01AB1234", "reason": "   "}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("reason", res.json()["detail"])

    def test_post_invalid_category_rejected(self):
        res = self.add_watch(category="NOPE")
        self.assertEqual(res.status_code, 400)

    def test_post_invalid_priority_rejected(self):
        res = self.add_watch(priority="URGENT")
        self.assertEqual(res.status_code, 400)

    def test_post_duplicate_409(self):
        self.add_watch("GJ01AB1234")
        res = self.add_watch("GJ 01 AB 1234")  # same normalized plate
        self.assertEqual(res.status_code, 409)

    def test_get_watchlist_plate(self):
        self.add_watch("GJ01AB1234")
        res = self.client.get("/api/watchlist/GJ01AB1234")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["normalized_plate"], "GJ01AB1234")

    def test_get_watchlist_plate_raw_form(self):
        self.add_watch("GJ01AB1234")
        res = self.client.get("/api/watchlist/GJ 01 AB 1234")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["normalized_plate"], "GJ01AB1234")

    def test_get_watchlist_missing_404(self):
        res = self.client.get("/api/watchlist/ZZ00ZZ0000")
        self.assertEqual(res.status_code, 404)

    def test_patch_watchlist(self):
        self.add_watch("GJ01AB1234")
        res = self.client.patch(
            "/api/watchlist/GJ01AB1234",
            json={"priority": "CRITICAL", "notes": "escalated"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["priority"], "CRITICAL")
        self.assertEqual(body["notes"], "escalated")

    def test_patch_invalid_category_rejected(self):
        self.add_watch("GJ01AB1234")
        res = self.client.patch(
            "/api/watchlist/GJ01AB1234", json={"category": "NOPE"}
        )
        self.assertEqual(res.status_code, 400)

    def test_patch_missing_404(self):
        res = self.client.patch(
            "/api/watchlist/ZZ00ZZ0000", json={"priority": "LOW"}
        )
        self.assertEqual(res.status_code, 404)

    def test_delete_deactivates(self):
        self.add_watch("GJ01AB1234")
        res = self.client.delete("/api/watchlist/GJ01AB1234")
        self.assertEqual(res.status_code, 200)
        entry = self.client.get("/api/watchlist/GJ01AB1234").json()
        self.assertFalse(entry["active"])

    def test_delete_missing_404(self):
        res = self.client.delete("/api/watchlist/ZZ00ZZ0000")
        self.assertEqual(res.status_code, 404)

    def test_list_watchlist_filters(self):
        self.add_watch("GJ01AB1234", category="STOLEN")
        self.add_watch("MH12CD3456", category="WANTED")
        body = self.client.get(
            "/api/watchlist", params={"category": "WANTED"}
        ).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["normalized_plate"], "MH12CD3456")
# ---------------------------------------------------------------------------
# Phase 7: Alert endpoints
# ---------------------------------------------------------------------------
class TestAlertsAPI(APITestCase):
    def add_alert(self, plate="HR99ABV2812", **kw):
        self.add_camera("cam01")
        self.client.post(
            "/api/watchlist",
            json={
                "plate": plate,
                "reason": kw.get("reason", "Reported stolen vehicle"),
                "category": kw.get("category", "STOLEN"),
                "priority": kw.get("priority", "CRITICAL"),
            },
        )
        entry = self.repos.watchlist.get_watchlist_entry_by_plate(plate)
        alert = Alert(
            watchlist_entry_id=int(entry.id),
            normalized_plate=normalize_plate_text(plate),
            canonical_vehicle_id=kw.get("canonical_vehicle_id", 123),
            camera_id="cam01",
            plate_read_id=kw.get("plate_read_id"),
            vehicle_class=kw.get("vehicle_class", "car"),
            confidence=kw.get("confidence", 0.91),
            reason="Reported stolen vehicle",
            category=kw.get("category", "STOLEN"),
            priority=kw.get("priority", "CRITICAL"),
            timestamp="2026-01-01T00:00:00+00:00",
            status="NEW",
        )
        alert.id = self.repos.alerts.create_alert(alert)
        return alert

    def test_get_alerts_empty(self):
        res = self.client.get("/api/alerts")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 0)

    def test_get_alert(self):
        alert = self.add_alert()
        res = self.client.get(f"/api/alerts/{alert.id}")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["normalized_plate"], "HR99ABV2812")
        self.assertEqual(body["camera_id"], "cam01")
        self.assertEqual(body["priority"], "CRITICAL")
        self.assertEqual(body["status"], "NEW")

    def test_get_alert_missing_404(self):
        res = self.client.get("/api/alerts/99999")
        self.assertEqual(res.status_code, 404)

    def test_alert_filters(self):
        self.add_alert(plate="HR99ABV2812", priority="CRITICAL")
        self.add_alert(plate="GJ01AB1234", priority="HIGH")
        body = self.client.get(
            "/api/alerts", params={"priority": "HIGH"}
        ).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["normalized_plate"], "GJ01AB1234")

    def test_alert_status_update(self):
        alert = self.add_alert()
        res = self.client.patch(
            f"/api/alerts/{alert.id}/status", json={"status": "ACKNOWLEDGED"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ACKNOWLEDGED")

    def test_alert_invalid_status_rejected(self):
        alert = self.add_alert()
        res = self.client.patch(
            f"/api/alerts/{alert.id}/status", json={"status": "DONE"}
        )
        self.assertEqual(res.status_code, 400)

    def test_alert_status_missing_404(self):
        res = self.client.patch(
            "/api/alerts/99999/status", json={"status": "RESOLVED"}
        )
        self.assertEqual(res.status_code, 404)

    def test_credential_leakage_still_absent_phase7(self):
        self.add_alert()
        for url in ("/api/watchlist", "/api/alerts"):
            text = self.client.get(url).text
            self.assertNotIn("secret123", text, url)
            self.assertNotIn("rtsp://", text, url)

    def test_get_camera_playback_valid(self):
        self.add_camera("cam01")
        res = self.client.get("/api/cameras/cam01/playback")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["camera_id"], "cam01")
        self.assertEqual(body["playback_type"], "hls")
        self.assertEqual(body["playback_url"], "https://cctv.corp8.cloud/cam01/index.m3u8")
        self.assertTrue(body["available"])
        self.assertNotIn("rtsp://", res.text)
        self.assertNotIn("secret123", res.text)

    def test_get_camera_playback_unknown_404(self):
        res = self.client.get("/api/cameras/unknown999/playback")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)

