from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from time import time
from typing import Any, Protocol


@dataclass(frozen=True)
class RateLimitPolicy:
    """Configure global and route-specific application rate limits."""

    enabled: bool = False
    fail_open: bool = True
    trust_forwarded_for: bool = False
    global_requests: int = 120
    window_seconds: int = 60
    register_service_requests: int = 10
    health_check_requests: int = 60
    circuit_breaker_requests: int = 10


@dataclass(frozen=True)
class RateLimitDecision:
    """Describe the result of one rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_at: int


class RateLimiter(Protocol):
    async def check(
        self,
        client_id: str,
        scope: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Consume one request from a rate limit bucket."""
        ...

    async def close(self) -> None:
        """Close rate limiter resources."""
        ...


class NoOpRateLimiter:
    async def check(
        self,
        client_id: str,
        scope: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Allow every request when application rate limiting is disabled."""
        del client_id, scope
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            remaining=limit,
            retry_after_seconds=0,
            reset_at=int(time()) + window_seconds,
        )

    async def close(self) -> None:
        """Close no resources for the disabled limiter."""
        return None


class RedisRateLimiter:
    """Apply an atomic token bucket shared by every application replica."""

    _RATE_LIMIT_SCRIPT = """
local capacity = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local current_time = redis.call("TIME")
local now_ms = current_time[1] * 1000 + math.floor(current_time[2] / 1000)
local refill_per_ms = capacity / window_ms

local state = redis.call("HMGET", KEYS[1], "tokens", "updated_at")
local tokens = tonumber(state[1]) or capacity
local updated_at = tonumber(state[2]) or now_ms
local elapsed_ms = math.max(0, now_ms - updated_at)
tokens = math.min(capacity, tokens + elapsed_ms * refill_per_ms)

local allowed = 0
local retry_after_ms = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    retry_after_ms = math.ceil((1 - tokens) / refill_per_ms)
end

local reset_after_ms = math.ceil((capacity - tokens) / refill_per_ms)
redis.call("HSET", KEYS[1], "tokens", tokens, "updated_at", now_ms)
redis.call("PEXPIRE", KEYS[1], math.ceil(window_ms * 2))

return {allowed, math.floor(tokens), retry_after_ms, reset_after_ms, now_ms}
"""

    def __init__(self, redis_url: str, client: Any | None = None) -> None:
        """Create a lazy Redis-backed rate limiter."""
        self._redis_url = redis_url
        self._client = client

    async def _ensure_client(self) -> Any:
        """Create the Redis client lazily and return it."""
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def check(
        self,
        client_id: str,
        scope: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Atomically refill and consume a token from a Redis bucket."""
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("Rate limit and window must be positive")

        client = await self._ensure_client()
        raw_result = await client.eval(
            self._RATE_LIMIT_SCRIPT,
            1,
            self._key(client_id, scope),
            limit,
            window_seconds * 1000,
        )
        if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 5:
            raise RuntimeError("Redis returned an invalid rate limit result")

        allowed, remaining, retry_after_ms, reset_after_ms, now_ms = (int(value) for value in raw_result)
        retry_after_seconds = max(1, ceil(retry_after_ms / 1000)) if not allowed else 0
        reset_at = ceil((now_ms + reset_after_ms) / 1000)
        return RateLimitDecision(
            allowed=bool(allowed),
            limit=limit,
            remaining=max(0, remaining),
            retry_after_seconds=retry_after_seconds,
            reset_at=reset_at,
        )

    async def close(self) -> None:
        """Close the Redis client when it has been opened."""
        client = self._client
        if client is not None:
            await client.aclose()

    @staticmethod
    def _key(client_id: str, scope: str) -> str:
        """Build a non-identifying Redis key for one client and scope."""
        client_hash = sha256(client_id.encode("utf-8")).hexdigest()
        return f"rate-limit:{scope}:{client_hash}"
