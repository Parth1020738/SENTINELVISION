"""
SentinelVision - CameraStream: authenticated RTSP ingestion.

Phase 6: Camera Ingestion

Responsibilities
----------------
- Build the authenticated RTSP URL via the central credential module
  (``backend.camera.rtsp_credentials``) - never inline, never logged.
- Force RTSP over TCP via ``OPENCV_FFMPEG_CAPTURE_OPTIONS`` BEFORE the
  capture is opened (required for remote/NAT environments).
- Time frames with PTS (``cap.get(cv2.CAP_PROP_POS_MSEC)``) - never
  ``CAP_PROP_FPS``.
- Reconnect with exponential backoff: ~2s initial, doubling, capped at
  ~30s, reset after a successful connection; never a tight loop.
- Treat single read failures and decoder warnings ("Could not find ref
  with POC") as non-fatal: inter-frame gaps are normal on these feeds
  and scene discontinuities occur because feeds loop.

Security
--------
- The authenticated URL is built per (re)connection and is NEVER stored
  on the instance, logged, or included in exceptions.
- Only redacted, credential-free descriptions may appear in logs.
"""

import logging
import os
import time
from typing import Any, Callable, Optional, Tuple

import cv2

from backend.camera.rtsp_credentials import (
    DEFAULT_CATALOGUE_URL,
    RTCredentialError,
    build_authenticated_rtsp_url,
    describe_rtsp_target,
    fetch_camera_catalogue,
    redact_url,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------
RTSP_INITIAL_BACKOFF_S = 2.0     # ~2 seconds initial reconnect delay
RTSP_MAX_BACKOFF_S = 30.0        # exponential backoff cap ~30 seconds
DEFAULT_READ_FAILURE_LIMIT = 60  # consecutive failed reads before reconnect


def configure_rtsp_tcp(environ: Optional[dict] = None) -> None:
    """Force OpenCV/FFmpeg to use TCP for RTSP transport.

    MUST be called before ``cv2.VideoCapture`` opens an RTSP URL.
    """
    env = os.environ if environ is None else environ
    env["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def _fourcc_to_str(fourcc: int) -> str:
    """Convert an OpenCV FOURCC integer to its 4-character string."""
    try:
        return "".join(chr((int(fourcc) >> (8 * i)) & 0xFF) for i in range(4))
    except (TypeError, ValueError):
        return "unknown"


class CameraStream:
    """Authenticated, TCP-forced, PTS-timed RTSP camera stream.

    Parameters
    ----------
    camera_id : str
        Dynamic camera identifier (e.g. ``"cam01"``).  Never hard-coded
        inside this module.
    catalogue : optional
        Pre-fetched camera catalogue payload; when provided its RTSP URL
        is preferred (credentials are injected into its authority).
    catalogue_fetcher : callable, optional
        ``fetcher(catalogue_url, timeout) -> payload`` used when no
        catalogue payload was supplied.  Defaults to a real HTTP fetch
        that tolerates failure (falls back to the official endpoint).
    capture_factory : callable, optional
        ``factory(url) -> capture`` (default ``cv2.VideoCapture``).
        Injectable for deterministic, camera-free unit tests.
    read_failure_limit : int
        Consecutive failed ``read()`` calls tolerated (inter-frame gaps
        are normal) before a reconnect is attempted.
    sleep_func : callable, optional
        Sleep implementation (default ``time.sleep``); injectable so
        backoff tests run instantly.
    environ_keys : mapping, optional
        Credential mapping override (``{ENV_RTSP_EMAIL: ..., ENV_RTSP_PASSWORD: ...}``).
        When ``None`` (production default) credentials are read from the
        real process environment.  Used by offline tests only.
    """

    def __init__(
        self,
        camera_id: str,
        catalogue: Any = None,
        catalogue_fetcher: Optional[Callable[..., Any]] = None,
        capture_factory: Optional[Callable[[str], Any]] = None,
        read_failure_limit: int = DEFAULT_READ_FAILURE_LIMIT,
        sleep_func: Optional[Callable[[float], None]] = None,
        environ_keys: Optional[dict] = None,
    ) -> None:
        self.camera_id = str(camera_id)
        self._catalogue = catalogue
        self._catalogue_fetcher = catalogue_fetcher
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._read_failure_limit = max(1, int(read_failure_limit))
        self._sleep = sleep_func or time.sleep
        self._environ = environ_keys

        self._capture: Any = None
        self._backoff_delay = RTSP_INITIAL_BACKOFF_S
        self._consecutive_read_failures = 0
        self._frames_read = 0
        self.last_connect_error: Optional[str] = None

    # ------------------------------------------------------------------
    # URL construction (central, credential-safe)
    # ------------------------------------------------------------------
    def _build_url(self) -> str:
        """Build the authenticated RTSP URL (credentials included).

        The URL is returned to the caller only; it is never stored on
        ``self`` and never logged.
        """
        catalogue = self._catalogue
        if catalogue is None and self._catalogue_fetcher is not None:
            catalogue = fetch_camera_catalogue(
                DEFAULT_CATALOGUE_URL, fetcher=self._catalogue_fetcher
            )
        return build_authenticated_rtsp_url(
            self.camera_id,
            catalogue=catalogue,
            environ=self._environ,
        )

    # ------------------------------------------------------------------
    # Connection + reconnect/backoff
    # ------------------------------------------------------------------
    def connect(self, max_attempts: Optional[int] = None) -> bool:
        """Open the stream, retrying with exponential backoff.

        Parameters
        ----------
        max_attempts : int, optional
            Maximum connection attempts (``None`` = retry forever with
            backoff, never a tight loop).

        Returns
        -------
        bool
            ``True`` when the capture is open; ``False`` when
            *max_attempts* was exhausted.
        """
        attempt = 0
        while True:
            attempt += 1
            # TCP must be configured BEFORE opening the capture.
            configure_rtsp_tcp()
            try:
                url = self._build_url()
            except RTCredentialError as exc:
                # Message contains no secrets by design.
                self.last_connect_error = str(exc)
                logger.error("RTSP credential error: %s", exc)
                raise

            target = describe_rtsp_target(self.camera_id)  # credential-free
            logger.info("Connecting to %s (attempt %d, TCP)", target, attempt)

            capture = self._capture_factory(url)
            opened = capture is not None and capture.isOpened()

            if opened:
                self._capture = capture
                self._consecutive_read_failures = 0
                self._backoff_delay = RTSP_INITIAL_BACKOFF_S  # reset backoff
                logger.info("Connected to %s", target)
                return True

            # Release and clean up any half-open capture.
            try:
                if capture is not None:
                    capture.release()
            except Exception:  # noqa: BLE001
                pass

            self.last_connect_error = (
                "capture could not be opened (possible 401/auth rejection)"
            )
            # The authenticated URL itself is never logged - only the
            # redacted target.
            logger.warning(
                "Failed to open %s (attempt %d): %s",
                target,
                attempt,
                self.last_connect_error,
            )

            if max_attempts is not None and attempt >= max_attempts:
                return False

            # Exponential backoff: ~2s -> 4s -> 8s ... capped at ~30s.
            delay = self._backoff_delay
            self._backoff_delay = min(self._backoff_delay * 2, RTSP_MAX_BACKOFF_S)
            logger.info("Reconnecting in %.1fs", delay)
            self._sleep(delay)

    # ------------------------------------------------------------------
    # Frame reading with PTS timing
    # ------------------------------------------------------------------
    def read(self) -> Tuple[bool, Optional[Any], Optional[float]]:
        """Read one frame.

        Returns
        -------
        (ok, frame, pts_ms)
            ``pts_ms`` is the PTS timestamp in milliseconds from
            ``cap.get(cv2.CAP_PROP_POS_MSEC)`` - the only sanctioned
            timing source.  ``CAP_PROP_FPS`` is never used for timing.
        """
        if self._capture is None:
            return False, None, None

        ok, frame = self._capture.read()
        if not ok or frame is None:
            # Inter-frame gaps are normal on looping feeds - do not fail
            # immediately; only reconnect after sustained failure.
            self._consecutive_read_failures += 1
            if self._consecutive_read_failures >= self._read_failure_limit:
                logger.warning(
                    "%d consecutive read failures on camera '%s'; reconnecting",
                    self._consecutive_read_failures,
                    self.camera_id,
                )
                self.reconnect()
            return False, None, None

        self._consecutive_read_failures = 0
        self._frames_read += 1
        pts_ms = self._capture.get(cv2.CAP_PROP_POS_MSEC)
        return True, frame, float(pts_ms) if pts_ms is not None else None

    def reconnect(self) -> bool:
        """Release the current capture and reconnect with backoff."""
        self.release()
        return self.connect()

    # ------------------------------------------------------------------
    # Stream metadata
    # ------------------------------------------------------------------
    @property
    def resolution(self) -> Optional[Tuple[int, int]]:
        """(width, height) of the open stream, or ``None``."""
        if self._capture is None:
            return None
        w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h) if w > 0 and h > 0 else None

    @property
    def codec(self) -> Optional[str]:
        """Four-character codec identifier, or ``None`` if unavailable."""
        if self._capture is None:
            return None
        return _fourcc_to_str(self._capture.get(cv2.CAP_PROP_FOURCC))

    @property
    def frames_read(self) -> int:
        """Total frames successfully read since construction."""
        return self._frames_read

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def release(self) -> None:
        """Release the underlying capture (idempotent)."""
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:  # noqa: BLE001
                pass
            self._capture = None

    def __enter__(self) -> "CameraStream":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def redacted_stream_report(camera_id: str) -> str:
    """Return a log-safe one-line description for reports.

    Convenience wrapper; exists so callers never hand-roll URL logging.
    """
    return redact_url(describe_rtsp_target(camera_id))
