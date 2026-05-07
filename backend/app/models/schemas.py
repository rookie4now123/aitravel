"""Backward-compatible schema imports.

New application code should import trip schemas from ``app.schemas.trip``.
"""

from app.schemas.trip import *  # noqa: F401,F403
