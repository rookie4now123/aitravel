from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import (
    REDIS_DEFAULT_TTL_SECONDS,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)

try:
    import redis
except ImportError:  # pragma: no cover - downgrade if redis package is not installed
    redis = None


logger = logging.getLogger(__name__)
_redis_client: Any | None = None
_redis_unavailable_logged = False


def _build_key(key: str) -> str:
    """Add a common prefix to cache keys to avoid conflicts between different projects."""
    return f"{REDIS_KEY_PREFIX}:{key}"


def _get_redis_client():
    """Lazy load the Redis client; return None if unavailable."""
    global _redis_client
    global _redis_unavailable_logged

    if not REDIS_ENABLED:
        return None
    if redis is None:
        if not _redis_unavailable_logged:
            logger.warning("Redis started, if no redis package installed, cache will be skipped.")
            _redis_unavailable_logged = True
        return None
    if _redis_client is not None:
        return _redis_client

    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as exc:  # pragma: no cover - Downgrade if connection fails
        if not _redis_unavailable_logged:
            logger.warning("Redis connection failed, cache functionality will be skipped: %s", exc)
            _redis_unavailable_logged = True
        return None


def get_cached_json(key: str) -> Any | None:
    """Read JSON cache; return None if hit fails or Redis is unavailable."""
    client = _get_redis_client()
    if client is None:
        return None

    try:
        raw_value = client.get(_build_key(key))
        if raw_value is None:
            return None
        return json.loads(raw_value)
    except Exception as exc:  # pragma: no cover - Downgrade if cache fails
        logger.debug("Reading Redis cache failed: %s", exc)
        return None


def set_cached_json(
    key: str,
    value: Any,
    expire_seconds: int | None = None,
) -> None:
    """Write JSON cache; skip if Redis is unavailable."""
    client = _get_redis_client()
    if client is None:
        return

    ttl = expire_seconds or REDIS_DEFAULT_TTL_SECONDS
    try:
        client.set(_build_key(key), json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as exc:  # pragma: no cover - Downgrade if cache fails
        logger.debug("Writing Redis cache failed: %s", exc)

