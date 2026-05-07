"""Backward-compatible API app import.

Prefer running ``uvicorn app.main:app`` for new code.
"""

from app.main import app, create_app

__all__ = ["app", "create_app"]
