"""
KALBI-2 Redis Caching Layer.

Provides a simple JSON-based cache-aside pattern on top of Redis,
used to avoid redundant API calls and expensive computations across
agent runs.
"""

import json
from typing import Any, Callable

import redis


class CacheService:
    """Lightweight Redis cache with JSON serialisation and TTL support.

    Usage::

        cache = CacheService("redis://localhost:6379/0")
        data  = cache.get_or_fetch(
            "kalshi:markets:active",
            fetch_fn=lambda: kalshi_client.get_active_markets(),
            ttl=120,
        )
    """

    def __init__(self, redis_url: str) -> None:
        """Initialise the cache service.

        Args:
            redis_url: A Redis connection string
                (e.g. ``redis://localhost:6379/0``).
        """
        self._client: redis.Redis = redis.from_url(
            redis_url, decode_responses=True
        )

    # ── Core operations ──────────────────────────────────────────────

    def get(self, key: str) -> dict | None:
        """Retrieve and JSON-deserialise a cached value.

        Args:
            key: The cache key.

        Returns:
            The deserialised dictionary, or ``None`` if the key does not
            exist or has expired.
        """
        raw: str | None = self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: dict, ttl: int = 300) -> None:
        """JSON-serialise and store a value with an expiry.

        Args:
            key: The cache key.
            value: A JSON-serialisable dictionary.
            ttl: Time-to-live in seconds (default 300 = 5 minutes).
        """
        self._client.setex(key, ttl, json.dumps(value))

    def invalidate(self, key: str) -> None:
        """Remove a key from the cache immediately.

        Args:
            key: The cache key to delete.
        """
        self._client.delete(key)

    # ── Cache-aside pattern ──────────────────────────────────────────

    def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], dict],
        ttl: int = 300,
    ) -> dict:
        """Return a cached value or compute, cache, and return it.

        This implements the *cache-aside* (lazy-loading) pattern:

        1. Try to read from Redis.
        2. On a cache miss, call ``fetch_fn()`` to produce the value.
        3. Store the result in Redis with the given TTL.
        4. Return the value.

        Args:
            key: The cache key.
            fetch_fn: A zero-argument callable that returns the value to
                cache.  Only invoked on a cache miss.
            ttl: Time-to-live in seconds (default 300).

        Returns:
            The cached or freshly computed dictionary.
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        value = fetch_fn()
        self.set(key, value, ttl=ttl)
        return value
