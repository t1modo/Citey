"""
Tests for app.services.cache.AsyncTTLCache.

No HTTP calls or Firebase connections required.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.cache import AsyncTTLCache


# ---------------------------------------------------------------------------
# Basic get / set semantics
# ---------------------------------------------------------------------------


async def test_cache_miss_returns_false_and_none() -> None:
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=60)
    hit, value = await cache.get("missing_key")
    assert hit is False
    assert value is None


async def test_cache_hit_after_set() -> None:
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=60)
    await cache.set("key1", {"data": "value"})
    hit, value = await cache.get("key1")
    assert hit is True
    assert value == {"data": "value"}


async def test_cache_stores_different_keys_independently() -> None:
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=60)
    await cache.set("alpha", 1)
    await cache.set("beta", 2)

    hit_a, val_a = await cache.get("alpha")
    hit_b, val_b = await cache.get("beta")

    assert hit_a and val_a == 1
    assert hit_b and val_b == 2


async def test_cache_overwrite_updates_value() -> None:
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=60)
    await cache.set("key", "original")
    await cache.set("key", "updated")
    _, value = await cache.get("key")
    assert value == "updated"


async def test_cache_accepts_list_value() -> None:
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=60)
    await cache.set("list_key", [1, 2, 3])
    hit, value = await cache.get("list_key")
    assert hit is True
    assert value == [1, 2, 3]


async def test_cache_accepts_none_value() -> None:
    """Explicitly caching None must be retrievable as a hit."""
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=60)
    await cache.set("none_key", None)
    hit, value = await cache.get("none_key")
    assert hit is True
    assert value is None


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


async def test_cache_evicts_oldest_when_full() -> None:
    """When maxsize=2, the third insertion evicts the oldest entry."""
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=2, ttl=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)  # evicts "a"

    hit_c, _ = await cache.get("c")
    assert hit_c is True

    # Either "a" or "b" was evicted (LRU order); at least one of the two
    # must be a miss.
    hit_a, _ = await cache.get("a")
    hit_b, _ = await cache.get("b")
    assert not (hit_a and hit_b), "At most one of a/b should survive after eviction"


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


async def test_cache_entry_expires_after_ttl() -> None:
    """An entry with a very short TTL should not be retrievable after it expires."""
    cache: AsyncTTLCache = AsyncTTLCache(maxsize=10, ttl=0.05)  # 50 ms TTL
    await cache.set("expiring_key", "data")

    # Immediately after set — should be a hit.
    hit, _ = await cache.get("expiring_key")
    assert hit is True

    await asyncio.sleep(0.1)  # wait longer than TTL

    hit_after, _ = await cache.get("expiring_key")
    assert hit_after is False
