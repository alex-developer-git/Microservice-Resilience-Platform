import sys
import types

import pytest

from app.cache import RedisHealthCache
from app.models import CircuitState, HealthCheckResult


class FakeRedisClient:
    def __init__(self) -> None:
        """Create a fake Redis client."""
        self.values: dict[str, str] = {}
        self.closed = False
        self.pinged = False

    async def get(self, key: str) -> str | None:
        """Return a value by key."""
        return self.values.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        """Store a value with a fake TTL."""
        self.values[key] = value

    async def ping(self) -> None:
        """Record that Redis was pinged."""
        self.pinged = True

    async def aclose(self) -> None:
        """Record that the client was closed."""
        self.closed = True


class FakeRedis:
    client = FakeRedisClient()
    created_with: tuple[str, bool] | None = None

    @classmethod
    def from_url(cls, redis_url: str, *, decode_responses: bool) -> FakeRedisClient:
        """Create a fake Redis client from a URL."""
        cls.created_with = (redis_url, decode_responses)
        return cls.client


@pytest.mark.asyncio
async def test_redis_health_cache_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify RedisHealthCache reads, writes, pings, and closes."""
    FakeRedis.client = FakeRedisClient()
    FakeRedis.created_with = None
    monkeypatch.setitem(sys.modules, "redis.asyncio", types.SimpleNamespace(Redis=FakeRedis))

    cache = RedisHealthCache("redis://redis:6379/0")
    result = HealthCheckResult(
        service_id="svc-1",
        service_name="orders",
        checked_at="2026-09-04T12:00:00Z",
        healthy=True,
        status_code=200,
        latency_ms=15.0,
        circuit_state=CircuitState.CLOSED,
    )

    assert await cache.get("svc-1") is None

    await cache.set(result, ttl_seconds=0)
    assert await cache.get("svc-1") is None

    await cache.set(result, ttl_seconds=30)
    cached = await cache.get("svc-1")
    await cache.ping()
    await cache.close()

    assert FakeRedis.created_with == ("redis://redis:6379/0", True)
    assert cached is not None
    assert cached.cached is True
    assert cached.service_id == "svc-1"
    assert FakeRedis.client.pinged is True
    assert FakeRedis.client.closed is True
