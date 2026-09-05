"""
SentinelVision - Database Package

Phase 6B: SQLite Persistence Layer

Provides a clean persistence layer for camera metadata, vehicle
events, plate reads, and zone counts.  Built on the Python standard
library ``sqlite3`` only — no third-party dependencies, no SQL inside
AI modules.

Modules
-------
models        Lightweight dataclasses representing database records.
database      ``Database`` class: connections, schema, transactions.
repositories  Repository classes + the ``record_*`` integration bridge.
"""

from backend.db.models import Camera, VehicleEvent, PlateRead, ZoneCount
from backend.db.database import Database, DEFAULT_DB_PATH
from backend.db.repositories import (
    CameraRepository,
    VehicleRepository,
    PlateRepository,
    ZoneRepository,
    EventRecorder,
    record_vehicle_event,
    record_plate_read,
    record_zone_count,
    register_camera,
)

__all__ = [
    "Camera",
    "VehicleEvent",
    "PlateRead",
    "ZoneCount",
    "Database",
    "DEFAULT_DB_PATH",
    "CameraRepository",
    "VehicleRepository",
    "PlateRepository",
    "ZoneRepository",
    "EventRecorder",
    "record_vehicle_event",
    "record_plate_read",
    "record_zone_count",
    "register_camera",
]
