from typing import Any, Protocol

from app.models import HealthCheckResult


class HealthCache(Protocol):
    async def get(self, service_id: str) -> HealthCheckResult | None:
        """Return a cached health check result when it exists."""
        ...

    async def set(self, result: HealthCheckResult, ttl_seconds: int) -> None:
        """Store a health check result for a limited time."""
        ...

    async def ping(self) -> None:
        """Verify that the cache backend is reachable."""
        ...

    async def close(self) -> None:
        """Close any cache backend resources."""
        ...


class RedisHealthCache:
    def __init__(self, redis_url: str) -> None:
        """Create a Redis-backed health result cache."""
        self._redis_url = redis_url
        self._client: Any | None = None

    async def _ensure_client(self) -> Any:
        """Create the Redis client lazily and return it."""
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def get(self, service_id: str) -> HealthCheckResult | None:
        """Read a cached health check result from Redis."""
        client = await self._ensure_client()
        raw = await client.get(self._key(service_id))
        if raw is None:
            return None
        return HealthCheckResult.model_validate_json(raw).model_copy(update={"cached": True})

    async def set(self, result: HealthCheckResult, ttl_seconds: int) -> None:
        """Write a health check result to Redis with a TTL."""
        if ttl_seconds <= 0:
            return
        client = await self._ensure_client()
        await client.setex(self._key(result.service_id), ttl_seconds, result.model_dump_json())

    async def ping(self) -> None:
        """Ping Redis to confirm cache readiness."""
        client = await self._ensure_client()
        await client.ping()

    async def close(self) -> None:
        """Close the Redis client when it has been opened."""
        if self._client is not None:
            await self._client.aclose()

    @staticmethod
    def _key(service_id: str) -> str:
        """Build the Redis key for a service health result."""
        return f"health:{service_id}"
