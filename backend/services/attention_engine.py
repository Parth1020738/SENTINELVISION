"""
SentinelVision - Operational Attention Engine

Phase 9.5: Central service responsible for calculating operational attention states and reasons.

Attention States:
- CRITICAL: Immediate operator attention required (critical alert, camera offline/failure).
- WATCH: Monitoring recommended (non-critical alert, active vehicle events, inactive AI).
- NORMAL: Camera operating normally without active alerts or degraded conditions.

Priority Order:
CRITICAL > WATCH > NORMAL
"""

from typing import Any, Optional, Tuple, NamedTuple


class AttentionResult(NamedTuple):
    attention_state: str
    attention_reason: Optional[str]


class AttentionEngine:
    """Calculates deterministic operational attention state for cameras."""

    @staticmethod
    def evaluate(
        camera: Any,
        repos: Optional[Any] = None,
        ai_active: Optional[bool] = None,
        custom_alerts: Optional[list] = None,
        custom_events: Optional[list] = None,
    ) -> AttentionResult:
        """
        Evaluates the operational attention state for a given camera.

        Args:
            camera: Camera model or object (NormalizedCamera, Camera, or dict)
            repos: Repositories container (optional database access)
            ai_active: Explicit AI active status override (optional)
            custom_alerts: Optional list of alert objects/dicts for direct testing
            custom_events: Optional list of vehicle events for direct testing

        Returns:
            AttentionResult(attention_state, attention_reason)
        """
        camera_id = str(getattr(camera, "camera_id", None) or (camera.get("camera_id") if isinstance(camera, dict) else ""))
        live = bool(getattr(camera, "live", False) if not isinstance(camera, dict) else camera.get("live", False))
        status = str(getattr(camera, "status", "") if not isinstance(camera, dict) else camera.get("status", ""))
        
        if ai_active is None:
            if isinstance(camera, dict):
                ai_active = camera.get("ai_active", False)
            else:
                ai_active = getattr(camera, "ai_active", False)

        # 1. Gather Alerts
        alerts = custom_alerts if custom_alerts is not None else []
        events = custom_events if custom_events is not None else []

        if repos is not None and camera_id:
            try:
                if custom_alerts is None and hasattr(repos, "alerts") and repos.alerts is not None:
                    alerts = repos.alerts.list_alerts(camera_id=camera_id)
            except Exception:
                pass

            try:
                if custom_events is None and hasattr(repos, "vehicles") and repos.vehicles is not None:
                    events = repos.vehicles.get_vehicle_events_by_camera(camera_id)
            except Exception:
                pass

        # -------------------------------------------------------------
        # Evaluate CRITICAL conditions (Highest Priority)
        # -------------------------------------------------------------
        # Condition A: Camera stream offline/failure
        if not live or status == "offline":
            return AttentionResult("CRITICAL", "Camera stream offline")

        # Condition B: Unacknowledged (NEW) Critical or High Priority Alert
        new_alerts = [a for a in alerts if (getattr(a, "status", None) or (a.get("status") if isinstance(a, dict) else "")) == "NEW"]
        for alert in new_alerts:
            prio = str(getattr(alert, "priority", "MEDIUM") if not isinstance(alert, dict) else alert.get("priority", "MEDIUM")).upper()
            if prio in ("CRITICAL", "HIGH"):
                reason = getattr(alert, "reason", None) or (alert.get("reason") if isinstance(alert, dict) else "")
                plate = getattr(alert, "normalized_plate", None) or (alert.get("normalized_plate") if isinstance(alert, dict) else "")
                detail = reason or plate or "Critical alert raised"
                return AttentionResult("CRITICAL", f"Active critical alert: {detail}")

        # Condition C: Any NEW alert (default critical if unhandled)
        if new_alerts:
            first_alert = new_alerts[0]
            reason = getattr(first_alert, "reason", None) or (first_alert.get("reason") if isinstance(first_alert, dict) else "")
            plate = getattr(first_alert, "normalized_plate", None) or (first_alert.get("normalized_plate") if isinstance(first_alert, dict) else "")
            detail = reason or plate or "New alert pending review"
            return AttentionResult("CRITICAL", f"Active critical alert: {detail}")

        # -------------------------------------------------------------
        # Evaluate WATCH conditions (Medium Priority)
        # -------------------------------------------------------------
        # Condition A: Acknowledged / Non-critical alerts present
        ack_alerts = [a for a in alerts if (getattr(a, "status", None) or (a.get("status") if isinstance(a, dict) else "")) == "ACKNOWLEDGED"]
        if ack_alerts:
            return AttentionResult("WATCH", "Recent non-critical alert under monitoring")

        # Condition B: Active vehicle events
        if events and len(events) > 0:
            return AttentionResult("WATCH", "Active vehicle activity detected")

        # Condition C: Camera is live but AI pipeline is inactive
        if live and not ai_active:
            return AttentionResult("WATCH", "AI processing inactive")

        # -------------------------------------------------------------
        # Evaluate NORMAL conditions (Lowest Priority)
        # -------------------------------------------------------------
        return AttentionResult("NORMAL", None)
