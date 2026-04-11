"""
Async-safe in-process TTL cache for external API responses.

Backed by cachetools.TTLCache (evicts entries after `ttl` seconds).
An asyncio.Lock prevents cache stampedes on cache misses.
"""

import asyncio
from typing import Any

from cachetools import TTLCache


class AsyncTTLCache:
    """Thin async wrapper around TTLCache with stampede protection."""

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()

    async def get(self, key: Any) -> tuple[bool, Any]:
        """Return (True, value) on hit, (False, None) on miss."""
        async with self._lock:
            try:
                return True, self._cache[key]
            except KeyError:
                return False, None

    async def set(self, key: Any, value: Any) -> None:
        async with self._lock:
            self._cache[key] = value
