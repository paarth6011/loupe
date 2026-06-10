from functools import lru_cache
from typing import Protocol

import redis

from app.config import get_settings


class Cache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    def incr(self, key: str, ttl_seconds: int) -> int: ...
    def delete(self, key: str) -> None: ...


class RedisCache:
    """Redis-backed cache. Degrades gracefully: any Redis error is swallowed so
    a cache outage never breaks a request (it just misses)."""

    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        try:
            return self._client.get(key)
        except redis.RedisError:
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self._client.set(key, value, ex=ttl_seconds)
        except redis.RedisError:
            pass

    def incr(self, key: str, ttl_seconds: int) -> int:
        """Atomically increment a counter, setting its TTL on first creation.
        Returns the new value, or 0 if Redis is unavailable (fail-open: a cache
        outage must not lock anyone out)."""
        try:
            value = self._client.incr(key)
            if value == 1:
                self._client.expire(key, ttl_seconds)
            return value
        except redis.RedisError:
            return 0

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except redis.RedisError:
            pass


class InMemoryCache:
    """Process-local cache used in tests (no Redis dependency)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = value

    def incr(self, key: str, ttl_seconds: int) -> int:
        value = int(self._store.get(key, "0")) + 1
        self._store[key] = str(value)
        return value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


@lru_cache
def get_cache() -> Cache:
    return RedisCache(get_settings().redis_url)
