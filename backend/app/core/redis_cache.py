import json
import logging
import os
import time
from typing import Any, Optional

from app.core.metrics import CACHE_OPERATIONS, REDIS_UP

logger = logging.getLogger("backend.core.redis_cache")

_redis_client = None
_last_failure = 0.0
RETRY_AFTER_SECONDS = 30


def get_redis_client():
    """Obtain or initialize the Redis client. If Redis is down, retry at most every 30s (graceful degradation)."""
    global _redis_client, _last_failure
    if _redis_client is not None:
        return _redis_client
    if _last_failure and time.time() - _last_failure < RETRY_AFTER_SECONDS:
        return None

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        client = redis.from_url(redis_url, socket_timeout=1.0, socket_connect_timeout=1.0)
        client.ping()
        _redis_client = client
        REDIS_UP.set(1)
        logger.info(f"Connected to Redis cache at {redis_url}")
    except Exception as e:
        _last_failure = time.time()
        REDIS_UP.set(0)
        logger.info(f"Redis is unavailable ({e}). Running without cache; will retry in {RETRY_AFTER_SECONDS}s.")
        return None
    return _redis_client


def _mark_broken(e: Exception) -> None:
    global _redis_client, _last_failure
    logger.debug(f"Redis operation failed: {e}")
    _redis_client = None
    _last_failure = time.time()
    REDIS_UP.set(0)


def redis_ping() -> bool:
    client = get_redis_client()
    if not client:
        return False
    try:
        client.ping()
        REDIS_UP.set(1)
        return True
    except Exception as e:
        _mark_broken(e)
        return False


def cache_get(key: str) -> Optional[Any]:
    """Retrieve and deserialize cached JSON value. Returns None on cache miss or error."""
    client = get_redis_client()
    if not client:
        CACHE_OPERATIONS.labels(result="bypass").inc()
        return None

    try:
        data = client.get(key)
        if data:
            CACHE_OPERATIONS.labels(result="hit").inc()
            return json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        CACHE_OPERATIONS.labels(result="miss").inc()
    except Exception as e:
        CACHE_OPERATIONS.labels(result="error").inc()
        _mark_broken(e)
    return None


def cache_set(key: str, value: Any, expire_seconds: int = 60) -> bool:
    """Serialize and store value in Redis with TTL. Fails gracefully if Redis is offline."""
    client = get_redis_client()
    if not client:
        return False

    try:
        client.set(key, json.dumps(value, default=str), ex=expire_seconds)
        return True
    except Exception as e:
        _mark_broken(e)
        return False


def cache_delete(key: str) -> bool:
    """Delete a key from Redis cache."""
    client = get_redis_client()
    if not client:
        return False
    try:
        client.delete(key)
        return True
    except Exception as e:
        _mark_broken(e)
        return False


def cache_delete_pattern(pattern: str) -> int:
    """Delete every key matching a glob pattern (e.g. 'news_feed:*')."""
    client = get_redis_client()
    if not client:
        return 0
    removed = 0
    try:
        for k in client.scan_iter(pattern):
            client.delete(k)
            removed += 1
    except Exception as e:
        _mark_broken(e)
    return removed


def cache_info() -> dict:
    """Small Redis status summary for the monitoring dashboard."""
    client = get_redis_client()
    if not client:
        return {"connected": False}
    try:
        info = client.info()
        return {
            "connected": True,
            "used_memory_human": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "keys": client.dbsize(),
            "uptime_seconds": info.get("uptime_in_seconds"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }
    except Exception as e:
        _mark_broken(e)
        return {"connected": False}
