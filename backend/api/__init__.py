"""
SentinelVision - FastAPI Backend API

Phase 6C: REST API on top of the SQLite persistence layer.

Architecture:  Camera / AI -> SQLite -> FastAPI -> Dashboard

The API only exposes data that already exists in the database layer.
No SQL lives in the route handlers — all access goes through
``backend.db.repositories``.
"""

from backend.api.main import app

__all__ = ["app"]

