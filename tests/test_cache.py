"""Unit tests for AsyncTTLCache."""

import asyncio
import time

import pytest
from unittest.mock import patch

from src.utils.cache import AsyncTTLCache


@pytest.mark.asyncio
async def test_set_and_get():
    """Test basic set/get."""
    cache = AsyncTTLCache()
    await cache.set("k", "v", ttl=60)
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_get_missing_key():
    """Test get returns None for missing key."""
    cache = AsyncTTLCache()
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_ttl_expiry():
    """Test that entries expire after TTL."""
    cache = AsyncTTLCache()
    with patch("src.utils.cache.time") as mock_time:
        mock_time.monotonic.return_value = 100.0
        await cache.set("k", "v", ttl=10)

        mock_time.monotonic.return_value = 105.0
        assert await cache.get("k") == "v"  # not expired

        mock_time.monotonic.return_value = 111.0
        assert await cache.get("k") is None  # expired


@pytest.mark.asyncio
async def test_invalidate():
    """Test explicit invalidation."""
    cache = AsyncTTLCache()
    await cache.set("k", "v", ttl=60)
    await cache.invalidate("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_invalidate_missing_key():
    """Test invalidating a non-existent key doesn't raise."""
    cache = AsyncTTLCache()
    await cache.invalidate("nope")  # should not raise


@pytest.mark.asyncio
async def test_clear():
    """Test clearing all entries."""
    cache = AsyncTTLCache()
    await cache.set("a", 1, ttl=60)
    await cache.set("b", 2, ttl=60)
    await cache.clear()
    assert await cache.get("a") is None
    assert await cache.get("b") is None


@pytest.mark.asyncio
async def test_concurrent_access():
    """Test concurrent reads and writes don't corrupt state."""
    cache = AsyncTTLCache()

    async def writer(key: str, val: int):
        await cache.set(key, val, ttl=60)

    async def reader(key: str):
        return await cache.get(key)

    await asyncio.gather(
        writer("x", 1),
        writer("y", 2),
        writer("z", 3),
    )

    results = await asyncio.gather(
        reader("x"),
        reader("y"),
        reader("z"),
    )
    assert results == [1, 2, 3]


@pytest.mark.asyncio
async def test_overwrite_value():
    """Test that setting the same key overwrites."""
    cache = AsyncTTLCache()
    await cache.set("k", "old", ttl=60)
    await cache.set("k", "new", ttl=60)
    assert await cache.get("k") == "new"
