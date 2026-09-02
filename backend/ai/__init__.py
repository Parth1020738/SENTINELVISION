"""
SentinelVision - AI Package

Phase 1: Detection and Tracking Foundation
"""

from backend.ai.vehicle_detector import VehicleDetector, CLASS_NAMES, ALLOWED_CLASS_IDS
from backend.ai.vehicle_tracker import VehicleTracker, VehicleObservation

__all__ = [
    "VehicleDetector",
    "VehicleTracker",
    "VehicleObservation",
    "CLASS_NAMES",
    "ALLOWED_CLASS_IDS",
]
