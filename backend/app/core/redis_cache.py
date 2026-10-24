import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("backend.core.redis_cache")

_redis_client = None
_redis_disabled = False


def get_redis_client():
    """Obtain or initialize Redis client with automatic graceful offline fallback."""
    global _redis_client, _redis_disabled
    if _redis_disabled:
        return None

    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis

            client = redis.from_url(redis_url, socket_timeout=1.0, socket_connect_timeout=1.0)
            client.ping()
            _redis_client = client
            logger.info(f"Connected to Redis cache at {redis_url}")
        except Exception as e:
            logger.info(f"Redis is unavailable ({e}). Gracefully running without Redis cache.")
            _redis_disabled = True
            return None

    return _redis_client


def cache_get(key: str) -> Optional[Any]:
    """Retrieve and deserialize cached JSON value. Returns None on cache miss or error."""
    client = get_redis_client()
    if not client:
        return None

    try:
        data = client.get(key)
        if data:
            return json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except Exception as e:
        logger.debug(f"Redis get failed for '{key}': {e}")
    return None


def cache_set(key: str, value: Any, expire_seconds: int = 60) -> bool:
    """Serialize and store value in Redis with TTL. Fails gracefully if Redis is offline."""
    client = get_redis_client()
    if not client:
        return False

    try:
        json_data = json.dumps(value, default=str)
        client.set(key, json_data, ex=expire_seconds)
        return True
    except Exception as e:
        logger.debug(f"Redis set failed for '{key}': {e}")
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
        logger.debug(f"Redis delete failed for '{key}': {e}")
        return False
