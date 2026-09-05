"""
SentinelVision - Camera Ingestion Tests (Phase 6)

Deterministic, fully offline unit tests for secure RTSP ingestion.
NO real camera, GPU, internet, or real credentials are required.

Covers
------
- email '@' -> %40 encoding
- password URL encoding (special characters preserved)
- credentials missing -> clean error, no secret leakage
- authenticated URL construction (default endpoint + catalogue URL)
- credentials / password never appear in log output or exceptions
- camera catalogue RTSP URL handling (prefer catalogue, inject authority)
- TCP OpenCV configuration (OPENCV_FFMPEG_CAPTURE_OPTIONS)
- PTS retrieval via CAP_PROP_POS_MSEC
- reconnect/backoff: ~2s start, doubling, ~30s cap, reset on success
"""

import io
import logging
import os
import unittest
import urllib.parse
from unittest import mock

from backend.camera.camera_stream import (
    RTSP_INITIAL_BACKOFF_S,
    RTSP_MAX_BACKOFF_S,
    CameraStream,
    configure_rtsp_tcp,
)
from backend.camera.rtsp_credentials import (
    DEFAULT_RTSP_HOST,
    DEFAULT_RTSP_PORT,
    ENV_RTSP_EMAIL,
    ENV_RTSP_PASSWORD,
    RTCredentialError,
    apply_credentials_to_rtsp_url,
    build_authenticated_rtsp_url,
    describe_rtsp_target,
    encode_userinfo_component,
    get_catalogue_rtsp_url,
    get_rtsp_credentials,
    redact_url,
)
from dotenv import load_dotenv

# Fake credential values used ONLY inside tests (never real ones).
TEST_EMAIL = "tester@example.com"
TEST_PASSWORD = "S3cret!Pass"


def _fake_env(**overrides):
    env = {
        ENV_RTSP_EMAIL: TEST_EMAIL,
        ENV_RTSP_PASSWORD: TEST_PASSWORD,
    }
    env.update(overrides)
    # Remove keys explicitly set to None.
    return {k: v for k, v in env.items() if v is not None}


class FakeCapture:
    """Offline stand-in for cv2.VideoCapture."""

    def __init__(self, opened=True, frames=3, pts_sequence=None, fourcc="H264"):
        self._opened = opened
        self._frames = frames
        self._pts = list(pts_sequence) if pts_sequence else []
        self._fourcc = fourcc
        self.released = False
        self.opened_with_url = None

    def isOpened(self):
        return self._opened

    def read(self):
        if self._frames > 0:
            self._frames -= 1
            import numpy as np

            return True, np.zeros((4, 4, 3), dtype=np.uint8)
        return False, None

    def get(self, prop):
        if prop == 0:  # cv2.CAP_PROP_POS_MSEC
            return self._pts.pop(0) if self._pts else 0.0
        if prop == 6:  # cv2.CAP_PROP_FOURCC
            chars = self._fourcc.encode("ascii")
            return sum(b << (8 * i) for i, b in enumerate(chars))
        if prop == 3:  # width
            return 1920
        if prop == 4:  # height
            return 1080
        return 0.0

    def release(self):
        self.released = True
        self._opened = False


# ---------------------------------------------------------------------------
# URL encoding behaviour
# ---------------------------------------------------------------------------
class TestURLEncoding(unittest.TestCase):
    def test_email_at_sign_encoded(self):
        self.assertEqual(
            encode_userinfo_component("you@example.com"), "you%40example.com"
        )

    def test_password_special_characters_encoded(self):
        raw = "p@ss word/1#2$3&=+?%,;:'\"[]<>|\\^`{}"
        encoded = encode_userinfo_component(raw)
        # Round trip must restore the exact password.
        self.assertEqual(urllib.parse.unquote(encoded), raw)
        # No raw reserved character may survive encoding ('%' appears only
        # as the escape character itself).
        for ch in "@ /#&=+?,;:'\"[]<>|\\^`{}":
            self.assertNotIn(ch, encoded)
        self.assertNotIn("%,", encoded)  # raw percent-comma must be encoded

    def test_password_with_at_sign_round_trip(self):
        encoded = encode_userinfo_component("a@b:c")
        self.assertEqual(encoded, "a%40b%3Ac")
        self.assertEqual(urllib.parse.unquote(encoded), "a@b:c")

    def test_encoded_values_are_url_safe(self):
        encoded = encode_userinfo_component("S3cret!Pass")
        self.assertNotIn("!", encoded)


# ---------------------------------------------------------------------------
# Credential retrieval
# ---------------------------------------------------------------------------
class TestCredentialRetrieval(unittest.TestCase):
    def test_credentials_missing_email_raises_without_secret(self):
        with self.assertRaises(RTCredentialError) as ctx:
            get_rtsp_credentials(_fake_env(**{ENV_RTSP_EMAIL: None}))
        self.assertNotIn(TEST_PASSWORD, str(ctx.exception))
        self.assertNotIn(TEST_EMAIL, str(ctx.exception))

    def test_credentials_missing_password_raises_without_secret(self):
        with self.assertRaises(RTCredentialError) as ctx:
            get_rtsp_credentials(_fake_env(**{ENV_RTSP_PASSWORD: None}))
        self.assertNotIn(TEST_PASSWORD, str(ctx.exception))

    def test_missing_env_entirely_raises(self):
        with self.assertRaises(RTCredentialError):
            get_rtsp_credentials({})

    def test_credentials_read_from_mapping(self):
        email, password = get_rtsp_credentials(_fake_env())
        self.assertEqual(email, TEST_EMAIL)
        self.assertEqual(password, TEST_PASSWORD)


# ---------------------------------------------------------------------------
# Authenticated URL construction
# ---------------------------------------------------------------------------
class TestAuthenticatedURLConstruction(unittest.TestCase):
    def test_default_endpoint_construction(self):
        url = build_authenticated_rtsp_url("cam07", environ=_fake_env())
        self.assertEqual(
            url,
            "rtsp://tester%40example.com:S3cret%21Pass@"
            f"{DEFAULT_RTSP_HOST}:{DEFAULT_RTSP_PORT}/stream/cam07",
        )

    def test_camera_id_dynamic(self):
        url = build_authenticated_rtsp_url("gate-99-x", environ=_fake_env())
        self.assertTrue(url.endswith("/stream/gate-99-x"))

    def test_authority_of_catalogue_url_gets_credentials(self):
        catalogue = {
            "cameras": [
                {"id": "cam03", "url": "rtsp://203.0.113.5:8554/stream/cam03"}
            ]
        }
        url = build_authenticated_rtsp_url(
            "cam03", catalogue=catalogue, environ=_fake_env()
        )
        self.assertEqual(
            url,
            "rtsp://tester%40example.com:S3cret%21Pass@"
            "203.0.113.5:8554/stream/cam03",
        )

    def test_existing_credentials_in_url_are_replaced(self):
        url = apply_credentials_to_rtsp_url(
            "rtsp://olduser:oldpass@203.0.113.5:8554/stream/cam01",
            TEST_EMAIL,
            TEST_PASSWORD,
        )
        self.assertNotIn("olduser", url)
        self.assertNotIn("oldpass", url)
        self.assertIn("tester%40example.com:S3cret%21Pass@", url)


# ---------------------------------------------------------------------------
# Log safety: credentials must never appear in log output
# ---------------------------------------------------------------------------
class TestCredentialLogSafety(unittest.TestCase):
    def _capture_logs(self, fn):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger()
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            fn()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        return stream.getvalue()

    def test_connect_failure_log_never_contains_credentials(self):
        def failing_factory(url):
            cap = FakeCapture(opened=False)
            cap.opened_with_url = url
            return cap

        def run():
            stream = CameraStream(
                "cam01",
                capture_factory=failing_factory,
                sleep_func=lambda _d: None,
                environ_keys=_fake_env(),
            )
            stream.connect(max_attempts=2)

        output = self._capture_logs(run)
        self.assertNotIn(TEST_PASSWORD, output)
        self.assertNotIn(TEST_EMAIL, output)
        self.assertNotIn("S3cret", output)
        # Credential-free host/path is still useful for debugging.
        self.assertIn(DEFAULT_RTSP_HOST, output)
        self.assertIn("/stream/cam01", output)

    def test_missing_credentials_log_never_contains_secrets(self):
        def run():
            stream = CameraStream("cam01", capture_factory=FakeCapture)
            with mock.patch.dict(os.environ):
                os.environ.pop(ENV_RTSP_EMAIL, None)
                os.environ.pop(ENV_RTSP_PASSWORD, None)
                with self.assertRaises(RTCredentialError):
                    stream.connect()

        output = self._capture_logs(run)
        self.assertNotIn(TEST_PASSWORD, output)
        self.assertNotIn(TEST_EMAIL, output)

    def test_redact_url_strips_userinfo(self):
        url = "rtsp://a%40b.com:pw@1.2.3.4:8554/stream/cam01"
        redacted = redact_url(url)
        self.assertNotIn("a%40b.com", redacted)
        self.assertNotIn("pw", redacted)
        self.assertEqual(redacted, "rtsp://1.2.3.4:8554/stream/cam01")

    def test_describe_target_is_credential_free(self):
        desc = describe_rtsp_target("cam01", environ=_fake_env())
        self.assertNotIn(TEST_EMAIL, desc)
        self.assertNotIn(TEST_PASSWORD, desc)
        self.assertIn("/stream/cam01", desc)


# ---------------------------------------------------------------------------
# Camera catalogue handling
# ---------------------------------------------------------------------------
class TestCatalogueHandling(unittest.TestCase):
    def test_catalogue_url_preferred(self):
        catalogue = [
            {"camera_id": "cam01", "rtsp": "rtsp://198.51.100.7:8554/stream/cam01"}
        ]
        url = build_authenticated_rtsp_url(
            "cam01", catalogue=catalogue, environ=_fake_env()
        )
        self.assertIn("198.51.100.7:8554/stream/cam01", url)
        self.assertIn("tester%40example.com:", url)

    def test_catalogue_missing_camera_falls_back_to_default_endpoint(self):
        catalogue = {"cameras": [{"id": "cam09", "url": "rtsp://198.51.100.7/x"}]}
        url = build_authenticated_rtsp_url(
            "cam01", catalogue=catalogue, environ=_fake_env()
        )
        self.assertIn(f"{DEFAULT_RTSP_HOST}:{DEFAULT_RTSP_PORT}/stream/cam01", url)

    def test_get_catalogue_rtsp_url_shapes(self):
        self.assertEqual(
            get_catalogue_rtsp_url(
                "cam02", {"cameras": [{"id": "cam02", "url": "rtsp://h/s/cam02"}]}
            ),
            "rtsp://h/s/cam02",
        )
        self.assertEqual(
            get_catalogue_rtsp_url(
                "cam02", [{"camera_id": "cam02", "rtsp": "rtsp://h2/x"}]
            ),
            "rtsp://h2/x",
        )
        self.assertIsNone(get_catalogue_rtsp_url("cam02", None))
        self.assertIsNone(get_catalogue_rtsp_url("camXX", []))


# ---------------------------------------------------------------------------
# TCP configuration
# ---------------------------------------------------------------------------
class TestTCPConfiguration(unittest.TestCase):
    def test_configure_rtsp_tcp_sets_env(self):
        env = {}
        configure_rtsp_tcp(env)
        self.assertEqual(env["OPENCV_FFMPEG_CAPTURE_OPTIONS"], "rtsp_transport;tcp")

    def test_connect_sets_tcp_before_capture_open(self):
        seen = []

        def factory(url):
            seen.append(os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS"))
            return FakeCapture(opened=True, frames=1)

        stream = CameraStream(
            "cam01",
            capture_factory=factory,
            sleep_func=lambda _d: None,
            catalogue={},
            environ_keys={
                ENV_RTSP_EMAIL: TEST_EMAIL,
                ENV_RTSP_PASSWORD: TEST_PASSWORD,
            },
        )
        self.assertTrue(stream.connect())
        self.assertEqual(seen, ["rtsp_transport;tcp"])


# ---------------------------------------------------------------------------
# PTS timing
# ---------------------------------------------------------------------------
class TestPTSTiming(unittest.TestCase):
    def _make_stream(self, cap, **kwargs):
        return CameraStream(
            "cam01",
            capture_factory=lambda url: cap,
            sleep_func=lambda _d: None,
            catalogue={},
            environ_keys={
                ENV_RTSP_EMAIL: TEST_EMAIL,
                ENV_RTSP_PASSWORD: TEST_PASSWORD,
            },
            **kwargs,
        )

    def test_read_returns_pts_from_pos_msec(self):
        cap = FakeCapture(opened=True, frames=4, pts_sequence=[0.0, 40.0, 80.0, 120.0])
        stream = self._make_stream(cap)
        stream.connect()

        pts_values = []
        for _ in range(4):
            ok, frame, pts_ms = stream.read()
            self.assertTrue(ok)
            pts_values.append(pts_ms)
        self.assertEqual(pts_values, [0.0, 40.0, 80.0, 120.0])

    def test_inter_frame_gap_is_not_fatal(self):
        # A run of failed reads (inter-frame gaps) must NOT trigger a
        # reconnect or raise; gaps are normal on looping feeds.
        cap = FakeCapture(opened=True, frames=0)
        stream = self._make_stream(cap, read_failure_limit=60)
        stream.connect()
        for _ in range(10):
            ok, frame, pts = stream.read()
            self.assertFalse(ok)
            self.assertIsNone(frame)
        self.assertIsNotNone(stream._capture)  # still connected, no reconnect


# ---------------------------------------------------------------------------
# Reconnect / backoff behaviour
# ---------------------------------------------------------------------------
class TestReconnectBackoff(unittest.TestCase):
    def _make_stream(self, factory, **kwargs):
        return CameraStream(
            "cam01",
            capture_factory=factory,
            sleep_func=kwargs.pop("sleep_func"),
            catalogue={},
            environ_keys={
                ENV_RTSP_EMAIL: TEST_EMAIL,
                ENV_RTSP_PASSWORD: TEST_PASSWORD,
            },
            **kwargs,
        )

    def test_backoff_sequence_and_cap(self):
        delays = []

        # Always-failing factory.
        stream = self._make_stream(
            lambda url: FakeCapture(opened=False), sleep_func=delays.append
        )
        self.assertFalse(stream.connect(max_attempts=8))
        self.assertEqual(
            delays,
            [2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0],  # 7 sleeps between 8 tries
        )

    def test_backoff_resets_after_success(self):
        attempts = {"n": 0}
        delays = []

        def factory(url):
            attempts["n"] += 1
            return FakeCapture(opened=(attempts["n"] >= 3), frames=1)

        stream = self._make_stream(factory, sleep_func=delays.append)
        self.assertTrue(stream.connect(max_attempts=5))
        self.assertEqual(delays, [2.0, 4.0])  # then success resets backoff

        # Force a later reconnect: backoff restarts at the initial value.
        cap2 = FakeCapture(opened=False)
        stream._capture_factory = lambda url: cap2
        delays.clear()
        stream.connect(max_attempts=2)
        self.assertEqual(delays, [RTSP_INITIAL_BACKOFF_S])

    def test_no_tight_reconnect_loop(self):
        # The first retry delay must be the ~2s initial backoff, never 0.
        delays = []
        stream = self._make_stream(
            lambda url: FakeCapture(opened=False), sleep_func=delays.append
        )
        stream.connect(max_attempts=2)
        self.assertGreaterEqual(delays[0], RTSP_INITIAL_BACKOFF_S - 0.001)
        self.assertGreater(RTSP_MAX_BACKOFF_S, RTSP_INITIAL_BACKOFF_S)

    def test_reconnect_after_read_failures_uses_backoff(self):
        caps = [FakeCapture(opened=True, frames=0), FakeCapture(opened=True, frames=0)]
        delays = []

        stream = self._make_stream(
            lambda url: caps.pop(0),
            sleep_func=delays.append,
            read_failure_limit=2,
        )
        stream.connect()
        # Two consecutive failed reads -> automatic reconnect.
        stream.read()
        stream.read()
        stream.read()  # crosses the failure limit, triggers reconnect
        # New capture from the list was used; success path recorded no delays.
        self.assertEqual(len(caps), 0)
        self.assertEqual(stream.frames_read, 0)


# ---------------------------------------------------------------------------
# .env loading behaviour
# ---------------------------------------------------------------------------
class TestDotEnvLoading(unittest.TestCase):
    """Verify .env loading works correctly alongside OS environment variables."""

    def test_env_file_loads_credentials(self):
        """When OS env vars are missing, .env values are loaded."""
        import tempfile

        # Clear any existing env vars
        saved = {}
        for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
            if key in os.environ:
                saved[key] = os.environ.pop(key)

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".env", delete=False
            ) as f:
                f.write("SENTINEL_RTSP_EMAIL=dummy@example.com\n")
                f.write("SENTINEL_RTSP_PASSWORD=dummy-password\n")
                env_path = f.name

            # Load the .env file directly
            load_dotenv(dotenv_path=env_path, override=False)

            # Verify credentials are now available
            email, password = get_rtsp_credentials()
            self.assertEqual(email, "dummy@example.com")
            self.assertEqual(password, "dummy-password")

            # Clean up temp file
            os.unlink(env_path)
        finally:
            # Restore original env vars
            for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
                os.environ.pop(key, None)
            os.environ.update(saved)

    def test_os_env_takes_precedence_over_dotenv(self):
        """Explicit OS env vars must take precedence over .env values."""
        import tempfile

        # Clear any existing env vars
        saved = {}
        for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
            if key in os.environ:
                saved[key] = os.environ.pop(key)

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".env", delete=False
            ) as f:
                f.write("SENTINEL_RTSP_EMAIL=dotenv@example.com\n")
                f.write("SENTINEL_RTSP_PASSWORD=dotenv-pass\n")
                env_path = f.name

            # Set OS env vars (should take precedence)
            os.environ[ENV_RTSP_EMAIL] = "os-env@example.com"
            os.environ[ENV_RTSP_PASSWORD] = "os-env-pass"

            # Load .env with override=False
            load_dotenv(dotenv_path=env_path, override=False)

            # OS env vars should win
            email, password = get_rtsp_credentials()
            self.assertEqual(email, "os-env@example.com")
            self.assertEqual(password, "os-env-pass")

            # Clean up temp file
            os.unlink(env_path)
        finally:
            # Restore original env vars
            for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
                os.environ.pop(key, None)
            os.environ.update(saved)

    def test_missing_credentials_still_produces_safe_error(self):
        """Missing credentials must produce the existing safe error."""
        # Clear any existing env vars
        saved = {}
        for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
            if key in os.environ:
                saved[key] = os.environ.pop(key)

        try:
            with self.assertRaises(RTCredentialError) as ctx:
                get_rtsp_credentials()
            # Error message must NOT contain credential values
            self.assertNotIn("dummy", str(ctx.exception).lower())
            self.assertIn(ENV_RTSP_EMAIL, str(ctx.exception))
        finally:
            # Restore original env vars
            os.environ.update(saved)

    def test_credentials_never_in_redacted_output(self):
        """Credentials must never appear in redacted URL output."""
        import tempfile

        # Clear any existing env vars
        saved = {}
        for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
            if key in os.environ:
                saved[key] = os.environ.pop(key)

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".env", delete=False
            ) as f:
                f.write("SENTINEL_RTSP_EMAIL=dummy@example.com\n")
                f.write("SENTINEL_RTSP_PASSWORD=dummy-password\n")
                env_path = f.name

            load_dotenv(dotenv_path=env_path, override=False)

            # Build URL and verify credentials are in it (for connection)
            url = build_authenticated_rtsp_url("cam01")
            self.assertIn("dummy%40example.com", url)
            self.assertIn("dummy-password", url)

            # But redacted output must NOT contain credentials
            redacted = redact_url(url)
            self.assertNotIn("dummy@example.com", redacted)
            self.assertNotIn("dummy-password", redacted)
            self.assertNotIn("dummy%40example.com", redacted)

            # describe_rtsp_target must also be safe
            desc = describe_rtsp_target("cam01")
            self.assertNotIn("dummy@example.com", desc)
            self.assertNotIn("dummy-password", desc)

            # Clean up temp file
            os.unlink(env_path)
        finally:
            # Restore original env vars
            for key in (ENV_RTSP_EMAIL, ENV_RTSP_PASSWORD):
                os.environ.pop(key, None)
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
