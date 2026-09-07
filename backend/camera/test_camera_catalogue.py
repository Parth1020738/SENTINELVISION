"""
Unit tests for backend.camera.camera_catalogue (Phase 9.3)
"""

import unittest
from backend.camera.camera_catalogue import CameraCatalogue, NormalizedCamera


class TestCameraCatalogue(unittest.TestCase):

    def test_parse_list_payload(self):
        payload = [
            {"id": "cam01", "name": "North Gate", "width": 1920, "height": 1080, "live": True},
            {"id": "cam02", "name": "South Gate", "resolution": "1280x720", "status": "online"},
        ]
        catalogue = CameraCatalogue(fetcher=lambda url, t: payload)
        cams = catalogue.refresh(force=True)

        self.assertEqual(len(cams), 2)
        cam1 = next(c for c in cams if c.camera_id == "cam01")
        cam2 = next(c for c in cams if c.camera_id == "cam02")

        self.assertEqual(cam1.name, "North Gate")
        self.assertEqual(cam1.resolution, "1920x1080")
        self.assertTrue(cam1.ai_active)

        self.assertEqual(cam2.name, "South Gate")
        self.assertEqual(cam2.resolution, "1280x720")
        self.assertFalse(cam2.ai_active)

    def test_parse_wrapped_dict_payload(self):
        payload = {
            "cameras": [
                {"camera_id": "cam03", "label": "East Perimeter", "live": False},
            ]
        }
        catalogue = CameraCatalogue(fetcher=lambda url, t: payload)
        cams = catalogue.refresh(force=True)

        self.assertEqual(len(cams), 1)
        self.assertEqual(cams[0].camera_id, "cam03")
        self.assertEqual(cams[0].name, "East Perimeter")
        self.assertFalse(cams[0].live)
        self.assertFalse(cams[0].ai_active)

    def test_catalogue_failure_fallback(self):
        def failing_fetcher(url, t):
            raise TimeoutError("Network timeout")

        catalogue = CameraCatalogue(fetcher=failing_fetcher)
        cams = catalogue.refresh(force=True)
        self.assertEqual(cams, [])

    def test_no_credentials_exposed(self):
        payload = [
            {
                "id": "cam01",
                "url": "rtsp://admin:secret123@103.250.160.189:8554/stream/cam01",
                "name": "Secure Cam",
            }
        ]
        catalogue = CameraCatalogue(fetcher=lambda url, t: payload)
        cams = catalogue.refresh(force=True)

        cam = cams[0]
        # Verify no secret attribute exists on NormalizedCamera
        self.assertFalse(hasattr(cam, "password"))
        self.assertFalse(hasattr(cam, "url"))
        self.assertNotIn("secret123", str(cam))


if __name__ == "__main__":
    unittest.main()
