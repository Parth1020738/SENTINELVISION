"""
SentinelVision - Services

Phase 7: service-layer components that orchestrate the persistence
layer (currently the watchlist alert engine).  Services never contain
SQL and never import YOLO / OpenCV / FastAPI.
"""

from backend.services.alert_engine import AlertEngine

__all__ = ["AlertEngine"]
