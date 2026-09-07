"""
SentinelVision - Event Hub Service

Phase 9.6: Centralized real-time event publisher for broadcasting application events
to connected WebSocket frontend clients.

Event Contract:
{
    "event_type": "alert_created" | "alert_status_changed" | "attention_changed" | "zone_count_changed" | "plate_read" | "vehicle_event",
    "timestamp": "2026-09-07T10:45:00Z",
    "camera_id": "cam01" | null,
    "data": { ... }
}
"""

import asyncio
import datetime
import json
import logging
from typing import Any, Dict, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _to_utc_iso(dt: Optional[datetime.datetime] = None) -> str:
    """Return an ISO 8601 timestamp string in UTC."""
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat()


def _sanitize_data(data: Any) -> Any:
    """Recursively strip any sensitive fields (passwords, RTSP URLs with credentials) from data payloads."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if k.lower() in ("password", "rtsp_url", "webrtc_url", "secret", "token"):
                continue
            sanitized[k] = _sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_data(item) for item in data]
    return data


class EventHub:
    """Manages active WebSocket clients and broadcasts application events."""

    def __init__(self) -> None:
        self._active_connections: Set[WebSocket] = set()

    def register(self, websocket: WebSocket) -> None:
        """Register a new WebSocket connection."""
        self._active_connections.add(websocket)
        logger.info("EventHub client connected (%d total)", len(self._active_connections))

    def unregister(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket connection."""
        self._active_connections.discard(websocket)
        logger.info("EventHub client disconnected (%d remaining)", len(self._active_connections))

    @property
    def client_count(self) -> int:
        """Return the count of active WebSocket clients."""
        return len(self._active_connections)

    async def broadcast_event(
        self,
        event_type: str,
        camera_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Broadcast a real-time event payload to all connected clients.
        
        This method is asynchronous, non-blocking, and handles client disconnections safely.
        """
        if not self._active_connections:
            return

        payload = {
            "event_type": event_type,
            "timestamp": timestamp or _to_utc_iso(),
            "camera_id": camera_id,
            "data": _sanitize_data(data or {}),
        }

        json_str = json.dumps(payload, default=str)
        stale_connections = []

        for connection in list(self._active_connections):
            try:
                await connection.send_text(json_str)
            except Exception as exc:
                logger.debug("Failed to send event to client, marking stale: %s", exc)
                stale_connections.append(connection)

        for connection in stale_connections:
            self.unregister(connection)

    def publish_sync(
        self,
        event_type: str,
        camera_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Synchronous helper to publish an event from synchronous code or AI threads.
        Schedules broadcast_event onto the active asyncio event loop if running.
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_event(event_type, camera_id, data, timestamp),
                    loop,
                )
        except RuntimeError:
            # No running loop in current thread
            pass


# Global EventHub singleton
event_hub = EventHub()
