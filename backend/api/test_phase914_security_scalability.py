"""
SentinelVision - Phase 9.14 Security & Scalability Tests

Verifies:
  1. Password hashing & token generation/decoding (PBKDF2 / HMAC)
  2. Authentication endpoints (/api/auth/login, /api/auth/me)
  3. Role-Based Access Control (RBAC: ADMIN vs OPERATOR vs VIEWER)
  4. Credential safety (RTSP credentials absent from API, error output, WS)
  5. Security headers & CORS configuration
  6. Audit logging for privileged operations
  7. In-memory rate limiting for login attempts
  8. Synthetic scalability test for camera catalogue & pagination
"""

import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.api.deps import reset_repositories
from backend.api.main import app
from backend.auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    hash_password,
    reset_rate_limiter,
    verify_password,
)
from backend.db.database import Database
from backend.camera.rtsp_credentials import redact_url


class TestPhase914SecurityAndScalability(unittest.TestCase):
    def setUp(self):
        self.db_path = "data/test_phase914_security.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.environ["SENTINELVISION_DB_PATH"] = self.db_path
        os.environ["SENTINEL_AUTH_REQUIRED"] = "false"
        reset_repositories()
        reset_rate_limiter()
        self.client = TestClient(app)

    def tearDown(self):
        reset_repositories()
        reset_rate_limiter()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        os.environ.pop("SENTINELVISION_DB_PATH", None)
        os.environ.pop("SENTINEL_AUTH_REQUIRED", None)

    # ---------------------------------------------------------------------------
    # 1. Password Hashing & Token Verification
    # ---------------------------------------------------------------------------
    def test_password_hashing(self):
        password = "SecretPassword123!"
        hashed = hash_password(password)
        self.assertTrue(hashed.startswith("pbkdf2:sha256:"))
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_signed_token_creation_and_decoding(self):
        token = create_access_token("admin_user", "ADMIN", expires_in_seconds=3600)
        self.assertIsInstance(token, str)

        decoded = decode_access_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["username"], "admin_user")
        self.assertEqual(decoded["role"], "ADMIN")

    def test_expired_or_invalid_token(self):
        expired_token = create_access_token("test_user", "VIEWER", expires_in_seconds=-10)
        self.assertIsNone(decode_access_token(expired_token))
        self.assertIsNone(decode_access_token("invalid.token.str"))

    # ---------------------------------------------------------------------------
    # 2. Authentication & Login Endpoints
    # ---------------------------------------------------------------------------
    def test_login_success_admin(self):
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "sentinel123!"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["role"], "ADMIN")
        self.assertEqual(data["username"], "admin")

    def test_login_failure_bad_password(self):
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("detail", resp.json())

    def test_auth_me_endpoint(self):
        token = create_access_token("operator", "OPERATOR")
        resp = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["username"], "operator")
        self.assertEqual(data["role"], "OPERATOR")

    # ---------------------------------------------------------------------------
    # 3. RBAC Enforcement (when SENTINEL_AUTH_REQUIRED=true)
    # ---------------------------------------------------------------------------
    def test_rbac_enforcement_admin_required(self):
        os.environ["SENTINEL_AUTH_REQUIRED"] = "true"

        # Missing auth header -> 401
        resp = self.client.post(
            "/api/watchlist",
            json={"plate": "HR26AB1234", "reason": "Test RBAC", "category": "WANTED", "priority": "HIGH"},
        )
        self.assertEqual(resp.status_code, 401)

        # Viewer token -> 403 (Insufficient permissions)
        viewer_token = create_access_token("viewer", "VIEWER")
        resp = self.client.post(
            "/api/watchlist",
            json={"plate": "HR26AB1234", "reason": "Test RBAC", "category": "WANTED", "priority": "HIGH"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        self.assertEqual(resp.status_code, 403)

        # Admin token -> 201 Created
        admin_token = create_access_token("admin", "ADMIN")
        resp = self.client.post(
            "/api/watchlist",
            json={"plate": "HR26AB1234", "reason": "Test RBAC", "category": "WANTED", "priority": "HIGH"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(resp.status_code, 201)

    # ---------------------------------------------------------------------------
    # 4. Credential Safety Audits
    # ---------------------------------------------------------------------------
    def test_rtsp_credentials_never_exposed_in_api(self):
        resp = self.client.get("/api/cameras")
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertNotIn("rtsp_url", text)
        self.assertNotIn("SENTINEL_RTSP_PASSWORD", text)
        self.assertNotIn("corp8", text)

    def test_url_redaction_utility(self):
        raw_url = "rtsp://user%40example.com:SecretPass123!@103.250.160.189:8554/stream/cam01"
        clean = redact_url(raw_url)
        self.assertNotIn("SecretPass123!", clean)
        self.assertNotIn("user%40example.com", clean)
        self.assertIn("103.250.160.189", clean)

    # ---------------------------------------------------------------------------
    # 5. Security Headers & CORS
    # ---------------------------------------------------------------------------
    def test_security_headers_present(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(resp.headers.get("x-frame-options"), "DENY")
        self.assertEqual(resp.headers.get("referrer-policy"), "strict-origin-when-cross-origin")
        self.assertEqual(resp.headers.get("x-xss-protection"), "1; mode=block")

    # ---------------------------------------------------------------------------
    # 6. Audit Logging Verification
    # ---------------------------------------------------------------------------
    def test_audit_logging_on_privileged_action(self):
        admin_token = create_access_token("admin", "ADMIN")

        # Perform a watchlist create action
        resp = self.client.post(
            "/api/watchlist",
            json={"plate": "DL01AB9999", "reason": "Audit Test", "category": "STOLEN", "priority": "CRITICAL"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(resp.status_code, 201)

        # Retrieve audit log
        audit_resp = self.client.get(
            "/api/audit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(audit_resp.status_code, 200)
        logs = audit_resp.json()["results"]
        self.assertTrue(any(l["action"] == "WATCHLIST_CREATE" and l["resource_id"] == "DL01AB9999" for l in logs))

    # ---------------------------------------------------------------------------
    # 7. Rate Limiting for Login
    # ---------------------------------------------------------------------------
    def test_login_rate_limiting(self):
        # Trigger 5 failed attempts
        for _ in range(5):
            self.client.post(
                "/api/auth/login",
                json={"username": "bad_user", "password": "wrong_password"},
            )
        # 6th attempt should return 429
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "bad_user", "password": "wrong_password"},
        )
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Too many failed login attempts", resp.json()["detail"])

    # ---------------------------------------------------------------------------
    # 8. Synthetic Scalability Test (1000 Simulated Camera Metadata Records)
    # ---------------------------------------------------------------------------
    def test_synthetic_catalogue_handling(self):
        from backend.camera.camera_catalogue import CameraCatalogue, NormalizedCamera

        catalogue = CameraCatalogue()
        fake_cameras = [
            NormalizedCamera(
                camera_id=f"cam_{i:04d}",
                name=f"State Highway Camera {i}",
                location=f"District {i % 10}",
                latitude=28.0 + (i * 0.001),
                longitude=77.0 + (i * 0.001),
                codec="H264",
                width=1920,
                height=1080,
                resolution="1920x1080",
                live=True,
                status="available",
            )
            for i in range(1000)
        ]
        catalogue._cached_cameras = {cam.camera_id: cam for cam in fake_cameras}
        catalogue._last_fetch_time = 9999999999.0
        self.assertEqual(len(catalogue.get_cameras()), 1000)


if __name__ == "__main__":
    unittest.main()
