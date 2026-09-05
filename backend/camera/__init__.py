"""
SentinelVision - Camera Ingestion Package (Phase 6)

Secure authenticated RTSP ingestion for the Sentinel Camera Grid.

Public API
----------
- :class:`CameraStream` - authenticated TCP/PTS RTSP stream with
  exponential-backoff reconnect.
- :func:`build_authenticated_rtsp_url` - THE central URL builder.
- :func:`get_rtsp_credentials` - environment-only credential retrieval.
- :func:`configure_rtsp_tcp` - force ``rtsp_transport;tcp`` for OpenCV.
"""

from backend.camera.camera_stream import CameraStream, configure_rtsp_tcp
from backend.camera.rtsp_credentials import (
    ENV_RTSP_EMAIL,
    ENV_RTSP_PASSWORD,
    RTCredentialError,
    build_authenticated_rtsp_url,
    describe_rtsp_target,
    encode_userinfo_component,
    get_rtsp_credentials,
    redact_url,
)

__all__ = [
    "CameraStream",
    "configure_rtsp_tcp",
    "ENV_RTSP_EMAIL",
    "ENV_RTSP_PASSWORD",
    "RTCredentialError",
    "build_authenticated_rtsp_url",
    "describe_rtsp_target",
    "encode_userinfo_component",
    "get_rtsp_credentials",
    "redact_url",
]
