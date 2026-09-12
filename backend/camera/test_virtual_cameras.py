import os
import unittest
from backend.camera.camera_catalogue import (
    NormalizedCamera,
    get_official_30_catalogue,
    get_virtual_30_catalogue,
    get_virtual_video_path,
    VIRTUAL_CAMERA_MAP,
)
from backend.ai.live_pipeline import LivePipeline
from backend.ai.multi_ingestion import CameraWorkerConfig, CameraIngestionWorker
from backend.db.database import Database
from backend.api.deps import Repositories
from backend.api.main import _build_camera_health_responses


class TestVirtualCameraIntegration(unittest.TestCase):
    def test_virtual_catalogue_structure(self):
        virtual_cams = get_virtual_30_catalogue()
        self.assertEqual(len(virtual_cams), 6)
        
        for cam in virtual_cams:
            self.assertTrue(cam.camera_id.startswith("v_cam"))
            self.assertTrue(cam.is_virtual)
            self.assertEqual(cam.status, "DEMO")
            self.assertIsNotNone(cam.name)
            self.assertIsNone(cam.latitude)
            self.assertIsNone(cam.longitude)

    def test_real_catalogue_unchanged(self):
        real_cams = get_official_30_catalogue()
        self.assertEqual(len(real_cams), 30)
        
        for cam in real_cams:
            self.assertTrue(cam.camera_id.startswith("cam"))
            self.assertFalse(cam.is_virtual)

    def test_video_path_resolution(self):
        v1_path = get_virtual_video_path("v_cam01")
        self.assertIsNotNone(v1_path)
        self.assertTrue(os.path.exists(v1_path))

        v2_path = get_virtual_video_path("v_cam02")
        self.assertIsNotNone(v2_path)
        self.assertTrue(os.path.exists(v2_path))

        v3_path = get_virtual_video_path("v_cam03")
        self.assertIsNotNone(v3_path)
        self.assertTrue(os.path.exists(v3_path))

        v30_path = get_virtual_video_path("v_cam30")
        self.assertIsNone(v30_path)

    def test_health_response_includes_real_cameras(self):
        db_file = os.path.abspath(r"scratch\test_health.db")
        if os.path.exists(db_file):
            try: os.remove(db_file)
            except Exception: pass
        db = Database(db_file)
        db.initialize()
        repos = Repositories.from_database(db)
        health_list = _build_camera_health_responses(repos)
        cam_ids = {h.camera_id for h in health_list}
        
        self.assertIn("cam01", cam_ids)
        self.assertIn("cam30", cam_ids)
        self.assertEqual(len(health_list), 30)
        try: os.remove(db_file)
        except Exception: pass

    def test_pipeline_reset_stream_state(self):
        db = Database(":memory:")
        db.initialize()
        pipeline = LivePipeline(camera_id="v_cam01", db=db, fetch_catalogue=False)
        
        pipeline._recorded_first.add(101)
        pipeline._persisted_plates.add((101, "HR19R6697"))
        
        pipeline.reset_stream_state()
        
        self.assertEqual(len(pipeline._recorded_first), 0)
        self.assertEqual(len(pipeline._persisted_plates), 0)


if __name__ == "__main__":
    unittest.main()
