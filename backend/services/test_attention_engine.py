"""
Unit tests for backend.services.attention_engine (Phase 9.5)
"""

import unittest
from backend.services.attention_engine import AttentionEngine


class DummyCamera:
    def __init__(self, camera_id="cam01", live=True, status="online", ai_active=True):
        self.camera_id = camera_id
        self.live = live
        self.status = status
        self.ai_active = ai_active


class DummyAlert:
    def __init__(self, status="NEW", priority="CRITICAL", reason="Watchlist Match", normalized_plate="ABC1234"):
        self.status = status
        self.priority = priority
        self.reason = reason
        self.normalized_plate = normalized_plate


class TestAttentionEngine(unittest.TestCase):

    def test_normal_condition(self):
        cam = DummyCamera(live=True, status="online", ai_active=True)
        res = AttentionEngine.evaluate(cam)
        self.assertEqual(res.attention_state, "NORMAL")
        self.assertIsNone(res.attention_reason)

    def test_watch_condition_ai_inactive(self):
        cam = DummyCamera(live=True, status="online", ai_active=False)
        res = AttentionEngine.evaluate(cam)
        self.assertEqual(res.attention_state, "WATCH")
        self.assertIn("AI processing inactive", res.attention_reason)

    def test_watch_condition_events(self):
        cam = DummyCamera(live=True, status="online", ai_active=True)
        events = [{"event_type": "DETECTED"}]
        res = AttentionEngine.evaluate(cam, custom_events=events)
        self.assertEqual(res.attention_state, "WATCH")
        self.assertIn("Active vehicle activity", res.attention_reason)

    def test_critical_condition_offline(self):
        cam = DummyCamera(live=False, status="offline", ai_active=False)
        res = AttentionEngine.evaluate(cam)
        self.assertEqual(res.attention_state, "CRITICAL")
        self.assertIn("Camera stream offline", res.attention_reason)

    def test_critical_condition_new_alert(self):
        cam = DummyCamera(live=True, status="online", ai_active=True)
        alerts = [DummyAlert(status="NEW", priority="HIGH", reason="Stolen Vehicle")]
        res = AttentionEngine.evaluate(cam, custom_alerts=alerts)
        self.assertEqual(res.attention_state, "CRITICAL")
        self.assertIn("Active critical alert", res.attention_reason)

    def test_critical_overrides_watch(self):
        # Offline (CRITICAL) + Events (WATCH) -> CRITICAL
        cam = DummyCamera(live=False, status="offline", ai_active=True)
        events = [{"event_type": "DETECTED"}]
        res = AttentionEngine.evaluate(cam, custom_events=events)
        self.assertEqual(res.attention_state, "CRITICAL")
        self.assertIn("Camera stream offline", res.attention_reason)

    def test_watch_overrides_normal(self):
        # AI inactive (WATCH) vs clean NORMAL -> WATCH
        cam = DummyCamera(live=True, status="online", ai_active=False)
        res = AttentionEngine.evaluate(cam)
        self.assertEqual(res.attention_state, "WATCH")

    def test_no_fake_critical_when_missing_data(self):
        # Standard live camera with missing optional data should be NORMAL
        cam = DummyCamera(live=True, status="online", ai_active=True)
        res = AttentionEngine.evaluate(cam, repos=None, custom_alerts=[], custom_events=[])
        self.assertEqual(res.attention_state, "NORMAL")
        self.assertIsNone(res.attention_reason)


if __name__ == "__main__":
    unittest.main()
