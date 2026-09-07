"""
SentinelVision - Alert Engine

Phase 7: service layer that turns ANPR plate reads into watchlist
alerts.

Flow
----
    ANPR result
        -> normalize plate (Phase 5 ``normalize_plate_text``)
        -> active watchlist lookup
        -> match?  -> duplicate/cooldown check -> create alert

Design
------
- Depends only on the repository layer (``backend.db.repositories``)
  and the Phase 5 normalization — no SQL here, no YOLO / OpenCV /
  FastAPI imports.
- Empty/invalid plate strings are ignored safely (returns ``None``).
- Duplicate suppression is time-based (timestamps, never FPS): a NEW
  alert for the same (normalized_plate, camera_id,
  canonical_vehicle_id) within the cooldown window is not duplicated;
  the existing alert is returned instead.
"""

import datetime
from typing import Optional

from backend.ai.plate_ocr import normalize_plate_text
from backend.db.database import Database, _to_utc_iso
from backend.db.models import Alert
from backend.db.repositories import AlertRepository, WatchlistRepository

# Default cooldown between duplicate NEW alerts (seconds).
DEFAULT_COOLDOWN_SECONDS = 60.0


def _parse_timestamp(value) -> Optional[datetime.datetime]:
    """Best-effort parse of an ISO-8601 (or epoch) timestamp."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(
            float(value), tz=datetime.timezone.utc
        )
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except ValueError:
        return None


class AlertEngine:
    """Generate alerts when ANPR results match the active watchlist.

    Usage::

        engine = AlertEngine(db)
        alert = engine.process_plate_read(
            plate="HR 99 ABV 2812",
            canonical_vehicle_id=123,
            camera_id="cam01",
            plate_read_id=45,
            vehicle_class="car",
            confidence=0.91,
            timestamp="2026-01-01T00:00:10+00:00",
        )

    ``process_plate_read`` returns the created (or existing, inside the
    cooldown window) :class:`Alert`, or ``None`` when the plate is
    empty/invalid or not on the active watchlist.
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        watchlist: Optional[WatchlistRepository] = None,
        alerts: Optional[AlertRepository] = None,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        if watchlist is None or alerts is None:
            if db is None:
                raise ValueError("AlertEngine requires a Database or repositories")
            watchlist = watchlist or WatchlistRepository(db)
            alerts = alerts or AlertRepository(db)
        self.watchlist = watchlist
        self.alerts = alerts
        self.cooldown_seconds = float(cooldown_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process_plate_read(
        self,
        plate: Optional[str],
        canonical_vehicle_id: Optional[int],
        camera_id: Optional[str],
        plate_read_id: Optional[int] = None,
        vehicle_class: Optional[str] = None,
        confidence: Optional[float] = None,
        timestamp=None,
    ) -> Optional[Alert]:
        """Process one ANPR result; return the alert, or ``None``.

        The plate is normalized with the existing Phase 5 logic before
        lookup, so ``"GJ 01 AB 1234"`` matches a ``GJ01AB1234`` entry.
        """
        # 1) Normalize using the existing Phase 5 implementation.
        normalized = normalize_plate_text(plate)
        # 2) Ignore empty / invalid plate strings safely.
        if not normalized:
            return None
        if canonical_vehicle_id is None or camera_id is None:
            return None

        # 3) Search the active watchlist.
        entry = self.watchlist.get_watchlist_entry_by_plate(normalized)
        if entry is None or not entry.active:
            return None

        # 4/5) Duplicate suppression within the cooldown window.
        existing = self._find_alert_in_cooldown(
            normalized, camera_id, int(canonical_vehicle_id), timestamp
        )
        if existing is not None:
            return existing

        # 6) Create the alert (reason/category/priority copied from the
        #    watchlist entry).
        alert = Alert(
            watchlist_entry_id=int(entry.id),
            normalized_plate=normalized,
            canonical_vehicle_id=int(canonical_vehicle_id),
            camera_id=camera_id,
            plate_read_id=plate_read_id,
            vehicle_class=vehicle_class,
            confidence=confidence,
            reason=entry.reason,
            category=entry.category,
            priority=entry.priority,
            timestamp=_to_utc_iso(timestamp),
            status="NEW",
        )
        alert.id = self.alerts.create_alert(alert)
        try:
            from backend.services.event_hub import event_hub
            event_hub.publish_sync(
                "alert_created",
                camera_id=camera_id,
                data={
                    "alert_id": alert.id,
                    "normalized_plate": normalized,
                    "canonical_vehicle_id": canonical_vehicle_id,
                    "reason": alert.reason,
                    "category": alert.category,
                    "priority": alert.priority,
                    "status": alert.status,
                },
            )
            event_hub.publish_sync(
                "attention_changed",
                camera_id=camera_id,
                data={
                    "attention_state": "CRITICAL",
                    "attention_reason": f"Active critical alert: {alert.reason or normalized}",
                },
            )
        except Exception:
            pass
        return alert

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _find_alert_in_cooldown(
        self,
        normalized_plate: str,
        camera_id: str,
        canonical_vehicle_id: int,
        timestamp,
    ) -> Optional[Alert]:
        """Return the most recent NEW alert if *timestamp* falls inside
        its cooldown window (time-based, never FPS)."""
        recent = self.alerts.find_recent_new_alert(
            normalized_plate, camera_id, canonical_vehicle_id
        )
        if recent is None:
            return None

        now = _parse_timestamp(timestamp)
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        seen = _parse_timestamp(recent.timestamp)
        if seen is None:
            # Unparseable stored timestamp: do not suppress.
            return None

        elapsed = (now - seen).total_seconds()
        if elapsed < 0:
            # Out-of-order/clock skew: treat as inside the cooldown.
            return recent
        if elapsed <= self.cooldown_seconds:
            return recent
        return None
