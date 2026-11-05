"""
In-process TTL cache for external API responses.

Backed by cachetools.TTLCache (evicts entries after `ttl` seconds). Guarded by
a threading.Lock rather than an asyncio.Lock: cron jobs run on worker threads
with their own event loops, and an asyncio.Lock is bound to a single loop.
The critical sections are plain dict operations, so a thread lock never
blocks the event loop for any meaningful time.
"""

import threading
from typing import Any

from cachetools import TTLCache


class AsyncTTLCache:
    """Async-friendly, thread-safe wrapper around TTLCache."""

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    async def get(self, key: Any) -> tuple[bool, Any]:
        """Return (True, value) on hit, (False, None) on miss."""
        with self._lock:
            try:
                return True, self._cache[key]
            except KeyError:
                return False, None

    async def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._cache[key] = value
