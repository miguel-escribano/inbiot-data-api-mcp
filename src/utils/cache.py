"""Async TTL cache for API responses."""

import asyncio
import time
from typing import Any, Optional


class AsyncTTLCache:
    """Simple async-safe TTL cache using monotonic clock."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get a value if it exists and hasn't expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: float) -> None:
        """Set a value with a TTL in seconds."""
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    async def invalidate(self, key: str) -> None:
        """Remove a specific key."""
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Remove all entries."""
        async with self._lock:
            self._store.clear()
