"""Backward-compatible config imports.

New application code should import from ``app.core.config``.
"""

from app.core.config import *  # noqa: F401,F403
