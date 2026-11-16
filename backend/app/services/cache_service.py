from __future__ import annotations

import json
import logging
import threading
import time
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
_redis_lock = threading.Lock()
_redis_client: Any | None = None
_redis_unavailable_logged = False
_redis_retry_after: float = 0.0
_REDIS_RETRY_COOLDOWN_SECONDS = 30.0


def _build_key(key: str) -> str:
    """Add a common prefix to cache keys to avoid conflicts between different projects."""
    return f"{REDIS_KEY_PREFIX}:{key}"


def _get_redis_client():
    """Thread-safe lazy loader for the Redis client with failure backoff."""
    global _redis_client
    global _redis_unavailable_logged
    global _redis_retry_after

    if not REDIS_ENABLED:
        return None
    if redis is None:
        if not _redis_unavailable_logged:
            logger.warning("Redis enabled, but redis package is not installed; cache will be skipped.")
            _redis_unavailable_logged = True
        return None

    if _redis_client is not None:
        return _redis_client

    now = time.monotonic()
    if now < _redis_retry_after:
        return None

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        now = time.monotonic()
        if now < _redis_retry_after:
            return None

        try:
            client = redis.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
            client.ping()
            _redis_client = client
            _redis_unavailable_logged = False
            _redis_retry_after = 0.0
            return _redis_client
        except Exception as exc:  # pragma: no cover - Downgrade if connection fails
            _redis_retry_after = time.monotonic() + _REDIS_RETRY_COOLDOWN_SECONDS
            if not _redis_unavailable_logged:
                logger.warning("Redis connection failed, cache functionality will be skipped: %s", exc)
                _redis_unavailable_logged = True
            return None


def close_redis_client() -> None:
    """Close the Redis client cleanly on application shutdown."""
    global _redis_client
    with _redis_lock:
        if _redis_client is not None:
            try:
                _redis_client.close()
            except Exception:
                pass
            _redis_client = None


def get_cached_json(key: str) -> Any | None:
    """Read JSON cache; return None on miss or if Redis is unavailable."""
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