"""
SentinelVision - API dependencies / wiring

Phase 6C: A tiny helper module that connects the API to the EXISTING
database layer.  No SQL here, no new persistence implementation —
just the ``Database`` + repository bundle used by the routes.

Database path resolution (in order):
  1. ``SENTINELVISION_DB_PATH`` environment variable (used by tests)
  2. ``data/sentinelvision.db`` (the production default)

Connections are opened per operation by ``backend.db.database``;
nothing is kept permanently open.
"""

import os
import threading
from dataclasses import dataclass
from typing import Optional

from backend.db.database import Database
from backend.db.repositories import (
    AlertRepository,
    CameraRepository,
    GlobalVehicleRepository,
    PlateRepository,
    VehicleRepository,
    WatchlistRepository,
    ZoneRepository,
)

_DB_PATH_ENV_VAR = "SENTINELVISION_DB_PATH"


@dataclass
class Repositories:
    """Bundle of the Phase 6B repositories plus Phase 7 watchlist/alert
    repositories and Phase 9.10 global vehicle tracking over one Database."""

    db: Database
    cameras: CameraRepository
    vehicles: VehicleRepository
    plates: PlateRepository
    zones: ZoneRepository
    watchlist: WatchlistRepository
    alerts: AlertRepository
    global_vehicles: GlobalVehicleRepository

    @classmethod
    def from_database(cls, db: Database) -> "Repositories":
        return cls(
            db=db,
            cameras=CameraRepository(db),
            vehicles=VehicleRepository(db),
            plates=PlateRepository(db),
            zones=ZoneRepository(db),
            watchlist=WatchlistRepository(db),
            alerts=AlertRepository(db),
            global_vehicles=GlobalVehicleRepository(db),
        )


def get_db_path() -> str:
    """Resolve the database path (env override or default)."""
    return os.environ.get(_DB_PATH_ENV_VAR, "data/sentinelvision.db")


_default_lock = threading.Lock()
_default_repositories: Optional[Repositories] = None


def _build_repositories() -> Repositories:
    db = Database(get_db_path())
    db.initialize()  # idempotent, safe
    return Repositories.from_database(db)


def get_repositories() -> Repositories:
    """FastAPI dependency: lazily create/reuse the repository bundle."""
    global _default_repositories
    if _default_repositories is None:
        with _default_lock:
            if _default_repositories is None:
                _default_repositories = _build_repositories()
    return _default_repositories


def reset_repositories() -> None:
    """Forget the cached bundle (used by tests / reconfiguration)."""
    global _default_repositories
    with _default_lock:
        _default_repositories = None
