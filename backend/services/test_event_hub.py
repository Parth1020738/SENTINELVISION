"""
Unit tests for backend.services.event_hub (Phase 9.6)
"""

import asyncio
import json
import unittest
from backend.services.event_hub import EventHub, _sanitize_data


class DummyWebSocket:
    def __init__(self, should_fail: bool = False):
        self.sent_messages = []
        self.should_fail = should_fail

    async def send_text(self, text: str):
        if self.should_fail:
            raise RuntimeError("Connection closed")
        self.sent_messages.append(text)


class TestEventHub(unittest.TestCase):

    def setUp(self):
        self.hub = EventHub()

    def test_register_unregister(self):
        ws1 = DummyWebSocket()
        ws2 = DummyWebSocket()
        self.hub.register(ws1)
        self.hub.register(ws2)
        self.assertEqual(self.hub.client_count, 2)

        self.hub.unregister(ws1)
        self.assertEqual(self.hub.client_count, 1)

    def test_broadcast_event(self):
        ws = DummyWebSocket()
        self.hub.register(ws)

        asyncio.run(
            self.hub.broadcast_event(
                event_type="alert_created",
                camera_id="cam01",
                data={"reason": "Stolen Vehicle", "priority": "HIGH"},
            )
        )

        self.assertEqual(len(ws.sent_messages), 1)
        msg = json.loads(ws.sent_messages[0])
        self.assertEqual(msg["event_type"], "alert_created")
        self.assertEqual(msg["camera_id"], "cam01")
        self.assertEqual(msg["data"]["reason"], "Stolen Vehicle")
        self.assertIn("timestamp", msg)

    def test_stale_client_cleanup(self):
        good_ws = DummyWebSocket(should_fail=False)
        bad_ws = DummyWebSocket(should_fail=True)

        self.hub.register(good_ws)
        self.hub.register(bad_ws)
        self.assertEqual(self.hub.client_count, 2)

        asyncio.run(
            self.hub.broadcast_event(
                event_type="attention_changed",
                camera_id="cam01",
                data={"attention_state": "CRITICAL"},
            )
        )

        self.assertEqual(self.hub.client_count, 1)
        self.assertEqual(len(good_ws.sent_messages), 1)

    def test_security_sanitization(self):
        raw_data = {
            "camera_id": "cam01",
            "password": "secret_password_123",
            "rtsp_url": "rtsp://admin:pass@10.0.0.1:8554/live",
            "reason": "Watchlist Match",
        }
        clean = _sanitize_data(raw_data)
        self.assertNotIn("password", clean)
        self.assertNotIn("rtsp_url", clean)
        self.assertEqual(clean["reason"], "Watchlist Match")

    def test_json_serialization(self):
        data = {"count": 42, "status": "active", "items": [1, 2, 3]}
        ws = DummyWebSocket()
        self.hub.register(ws)

        asyncio.run(self.hub.broadcast_event("zone_count_changed", data=data))
        self.assertEqual(len(ws.sent_messages), 1)
        parsed = json.loads(ws.sent_messages[0])
        self.assertEqual(parsed["data"]["count"], 42)


if __name__ == "__main__":
    unittest.main()
