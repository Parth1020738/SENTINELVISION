"""
SentinelVision - Secure RTSP credential and URL construction.

Phase 6: Camera Ingestion

This module is the SINGLE place in the project where authenticated
RTSP URLs are built.  No other module may concatenate credentials
into a URL string.

Official Sentinel Camera Grid contract
--------------------------------------
    RTSP:  rtsp://<email>:<password>@103.250.160.189:8554/stream/<id>
    HLS:   https://cctv.corp8.cloud/<id>/index.m3u8

Security rules enforced here
----------------------------
- Credentials come ONLY from environment variables:
      SENTINEL_RTSP_EMAIL
      SENTINEL_RTSP_PASSWORD
- Credentials are never hard-coded, never logged, never included in
  exception messages, and never written to test fixtures.
- The ``@`` in an email address MUST be percent-encoded (``%40``).
- All other special characters in the password are percent-encoded too
  (``urllib.parse.quote`` with ``safe=""``).
- Only a credential-free description of the URL may ever be logged.
"""

import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Central .env loading — single place in the project.
#
# Loads .env from the project root into os.environ.
# override=False (the default) means explicit OS environment variables
# ALWAYS take precedence over .env values.  This preserves the existing
# contract: real deployments set OS env vars; local development uses .env.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# Official Camera Grid contract constants
# ---------------------------------------------------------------------------
DEFAULT_RTSP_HOST = "103.250.160.189"
DEFAULT_RTSP_PORT = 8554
DEFAULT_CATALOGUE_URL = "https://cctv.corp8.cloud/cameras.json"

# Environment variable names (documented contract)
ENV_RTSP_EMAIL = "SENTINEL_RTSP_EMAIL"
ENV_RTSP_PASSWORD = "SENTINEL_RTSP_PASSWORD"
ENV_RTSP_HOST = "SENTINEL_RTSP_HOST"      # optional override, for tests only
ENV_RTSP_PORT = "SENTINEL_RTSP_PORT"      # optional override, for tests only


class RTCredentialError(RuntimeError):
    """Raised when RTSP credentials are missing or invalid.

    The exception message deliberately contains NO credential material.
    """


# ---------------------------------------------------------------------------
# Credential retrieval - environment variables ONLY
# ---------------------------------------------------------------------------
def get_rtsp_credentials(
    environ: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Read RTSP credentials from the environment.

    Parameters
    ----------
    environ : mapping, optional
        Environment mapping to read from (defaults to ``os.environ``).
        Injectable so tests can run without touching the real environment.

    Returns
    -------
    (email, password) : tuple[str, str]

    Raises
    ------
    RTCredentialError
        If either variable is missing or empty.  The message never
        contains the actual credential values.
    """
    env = os.environ if environ is None else environ
    email = env.get(ENV_RTSP_EMAIL, "").strip()
    password = env.get(ENV_RTSP_PASSWORD, "")

    if not email:
        raise RTCredentialError(
            f"Missing RTSP credentials: set the {ENV_RTSP_EMAIL} environment "
            f"variable (registered camera-grid email)."
        )
    if not password:
        raise RTCredentialError(
            f"Missing RTSP credentials: set the {ENV_RTSP_PASSWORD} "
            f"environment variable (camera-grid access password)."
        )
    if "@" not in email:
        raise RTCredentialError(
            f"{ENV_RTSP_EMAIL} does not look like an email address "
            f"(no '@' found)."
        )
    return email, password


# ---------------------------------------------------------------------------
# Percent-encoding (the ONLY sanctioned encoding for userinfo)
# ---------------------------------------------------------------------------
def encode_userinfo_component(value: str) -> str:
    """Percent-encode an RTSP username or password component.

    Uses ``urllib.parse.quote`` with ``safe=""`` so that EVERY reserved
    character is encoded:

        ``you@example.com``   -> ``you%40example.com``
        ``p@ss word/1#2$3``   -> ``p%40ss%20word%2F1%232%243``

    This preserves special characters in passwords exactly as required
    by the Camera Grid contract.
    """
    if value is None:
        return ""
    return urllib.parse.quote(str(value), safe="")


# ---------------------------------------------------------------------------
# Credential-free URL description (the only thing allowed in logs)
# ---------------------------------------------------------------------------
def redact_url(url: str) -> str:
    """Return *url* with any userinfo replaced (removed).

    Safe to call on any URL, even one that (accidentally) contains
    credentials.  Used defensively before any logging.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        if not parts.hostname:
            return url
        netloc = parts.hostname
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        return urllib.parse.urlunsplit(
            (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
        )
    except ValueError:
        return "<unparseable-url>"


def describe_rtsp_target(camera_id: str, environ: Optional[Dict[str, str]] = None) -> str:
    """Return a credential-free, log-safe description of a camera target."""
    env = os.environ if environ is None else environ
    host, port = _get_rtsp_host_port(env)
    return f"rtsp://{host}:{port}/stream/{camera_id} (credentials redacted)"


def _get_rtsp_host_port(environ: Dict[str, str]) -> Tuple[str, int]:
    """Resolve the RTSP host/port, preferring the official defaults."""
    host = environ.get(ENV_RTSP_HOST, DEFAULT_RTSP_HOST)
    port_raw = environ.get(ENV_RTSP_PORT, str(DEFAULT_RTSP_PORT))
    try:
        port = int(port_raw)
    except ValueError:
        port = DEFAULT_RTSP_PORT
    return host, port


# ---------------------------------------------------------------------------
# Base (unauthenticated) endpoint
# ---------------------------------------------------------------------------
def get_rtsp_endpoint(camera_id: str, environ: Optional[Dict[str, str]] = None) -> str:
    """Build the unauthenticated RTSP endpoint for *camera_id*.

    ``rtsp://<host>:<port>/stream/<camera_id>``

    The camera id stays fully dynamic - it is never hard-coded here.
    """
    env = os.environ if environ is None else environ
    host, port = _get_rtsp_host_port(env)
    return f"rtsp://{host}:{port}/stream/{camera_id}"


# ---------------------------------------------------------------------------
# Credential injection into an authority component
# ---------------------------------------------------------------------------
def apply_credentials_to_rtsp_url(
    rtsp_url: str,
    email: str,
    password: str,
) -> str:
    """Inject (or replace) credentials in the authority of *rtsp_url*.

    The scheme, host, port, path and query of the source URL are
    preserved; only the userinfo is (re)written with correctly
    percent-encoded values.  This means a catalogue-provided RTSP URL
    is reused verbatim - we never duplicate camera URLs around the
    project, we only ever inject credentials into the authority.

    Raises
    ------
    ValueError
        If the URL has no authority (host) component.
    """
    parts = urllib.parse.urlsplit(rtsp_url)
    if not parts.hostname:
        raise ValueError(
            "RTSP URL has no authority component: cannot inject credentials"
        )

    userinfo = (
        f"{encode_userinfo_component(email)}:{encode_userinfo_component(password)}"
    )
    netloc = parts.hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"

    return urllib.parse.urlunsplit(
        (parts.scheme, f"{userinfo}@{netloc}", parts.path, parts.query, parts.fragment)
    )


# ---------------------------------------------------------------------------
# Camera catalogue (official: GET https://cctv.corp8.cloud/cameras.json)
# ---------------------------------------------------------------------------
def fetch_camera_catalogue(
    catalogue_url: str = DEFAULT_CATALOGUE_URL,
    timeout: float = 5.0,
    fetcher=None,
) -> Any:
    """Fetch and JSON-decode the camera catalogue.

    ``fetcher`` is injectable for deterministic offline tests; by default
    a plain ``urllib`` GET is used.  Failures return ``None`` (the caller
    falls back to the official RTSP endpoint) - a missing catalogue is
    never fatal.
    """
    if fetcher is None:
        def fetcher(url: str, t: float) -> Any:
            import json

            with urllib.request.urlopen(url, timeout=t) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))

    try:
        return fetcher(catalogue_url, timeout)
    except Exception as exc:  # noqa: BLE001 - network/parse errors are non-fatal
        logger.info(
            "Camera catalogue unavailable (%s); using default endpoint",
            type(exc).__name__,
        )
        return None


def get_catalogue_rtsp_url(camera_id: str, catalogue: Any) -> Optional[str]:
    """Extract the RTSP URL for *camera_id* from a catalogue payload.

    Tolerates several payload shapes:
      ``{"cameras": [{"id": "cam01", "url": "rtsp://..."}]}``
      ``[{"camera_id": "cam01", "rtsp": "rtsp://..."}]``
    """
    if not catalogue:
        return None

    entries: List[Dict[str, Any]] = []
    if isinstance(catalogue, dict):
        for key in ("cameras", "camera", "items", "data"):
            value = catalogue.get(key)
            if isinstance(value, list):
                entries = value
                break
    elif isinstance(catalogue, list):
        entries = catalogue

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = (
            entry.get("id") or entry.get("camera_id") or entry.get("cameraId")
        )
        if str(entry_id) != str(camera_id):
            continue
        for url_key in ("url", "rtsp", "rtsp_url", "rtspUrl"):
            url = entry.get(url_key)
            if isinstance(url, str) and url.lower().startswith("rtsp://"):
                return url
    return None


# ---------------------------------------------------------------------------
# THE central URL builder - the only sanctioned entry point
# ---------------------------------------------------------------------------
def build_authenticated_rtsp_url(
    camera_id: str,
    email: Optional[str] = None,
    password: Optional[str] = None,
    catalogue: Any = None,
    environ: Optional[Dict[str, str]] = None,
) -> str:
    """Build the authenticated RTSP URL for *camera_id*.

    Behaviour
    ---------
    1. Credentials default to the environment variables
       ``SENTINEL_RTSP_EMAIL`` / ``SENTINEL_RTSP_PASSWORD``.
    2. If the catalogue contains an RTSP URL for this camera, that URL's
       scheme/host/path is reused and credentials are injected into its
       authority component.
    3. Otherwise the official endpoint
       ``rtsp://<host>:<port>/stream/<camera_id>`` is used.

    The returned URL CONTAINS credentials and must never be logged or
    stored.  Use :func:`redact_url` / :func:`describe_rtsp_target` for
    log output.

    Raises
    ------
    RTCredentialError
        When credentials are missing (message contains no secrets).
    """
    env = os.environ if environ is None else environ
    if email is None or password is None:
        env_email, env_password = get_rtsp_credentials(env)
        email = env_email if email is None else email
        password = env_password if password is None else password

    base_url = get_catalogue_rtsp_url(camera_id, catalogue)
    if base_url:
        # Reuse catalogue URL, inject credentials into its authority only.
        return apply_credentials_to_rtsp_url(base_url, email, password)

    return apply_credentials_to_rtsp_url(
        get_rtsp_endpoint(camera_id, env), email, password
    )
