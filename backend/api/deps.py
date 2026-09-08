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

from fastapi import Depends, HTTPException, Request

from backend.db.database import Database
from backend.db.repositories import (
    AlertRepository,
    AuditRepository,
    CameraHealthRepository,
    CameraRepository,
    GlobalVehicleRepository,
    PlateRepository,
    VehicleRepository,
    WatchlistRepository,
    ZoneRepository,
)
from backend.auth import (
    ROLE_HIERARCHY,
    decode_access_token,
    is_auth_required,
)

_DB_PATH_ENV_VAR = "SENTINELVISION_DB_PATH"


@dataclass
class Repositories:
    """Bundle of the Phase 6B repositories plus Phase 7 watchlist/alert
    repositories, Phase 9.10 global vehicle tracking, Phase 9.12 health, and Phase 9.14 audit repositories over one Database."""

    db: Database
    cameras: CameraRepository
    vehicles: VehicleRepository
    plates: PlateRepository
    zones: ZoneRepository
    watchlist: WatchlistRepository
    alerts: AlertRepository
    global_vehicles: GlobalVehicleRepository
    health: CameraHealthRepository
    audit: AuditRepository

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
            health=CameraHealthRepository(db),
            audit=AuditRepository(db),
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


# ---------------------------------------------------------------------------
# Phase 9.14: Authentication & RBAC Dependencies
# ---------------------------------------------------------------------------
def get_current_user(request: Request) -> Optional[dict]:
    """Resolve current user from Authorization header, query parameter, or session token.

    If auth is not required by environment (SENTINEL_AUTH_REQUIRED=false) and
    no auth token is present, returns a default guest user (ADMIN role for dev compatibility).
    If auth token is present (via header or query param), decodes token and enforces validity.
    If auth is required and no valid token is present, raises 401.
    """
    token: Optional[str] = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "token" in request.query_params:
        token = request.query_params.get("token", "").strip()

    if token:
        user = decode_access_token(token)
        if user:
            return user
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")

    if not is_auth_required():
        # Dev / PoC unauthenticated mode - default guest admin privileges
        return {"username": "system_guest", "role": "ADMIN"}

    raise HTTPException(status_code=401, detail="Authentication required")


def require_role(min_role: str):
    """FastAPI dependency factory enforcing a minimum role hierarchy level."""
    def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role", "VIEWER")
        user_level = ROLE_HIERARCHY.get(user_role, 0)
        required_level = ROLE_HIERARCHY.get(min_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: requires {min_role} role",
            )
        return user
    return role_checker

