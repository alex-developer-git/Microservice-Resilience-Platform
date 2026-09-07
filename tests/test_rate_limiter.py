import pytest

from app.rate_limiter import RedisRateLimiter


class RedisClientStub:
    def __init__(self, result: list[int]) -> None:
        self.result = result
        self.eval_calls: list[tuple[object, ...]] = []
        self.closed = False

    async def eval(self, *arguments: object) -> list[int]:
        """Return a prepared Lua result and record the request."""
        self.eval_calls.append(arguments)
        return self.result

    async def aclose(self) -> None:
        """Record that the fake Redis client was closed."""
        self.closed = True


@pytest.mark.asyncio
async def test_redis_rate_limiter_parses_an_allowed_token_bucket_result() -> None:
    """Verify Redis token bucket results become response metadata."""
    redis = RedisClientStub([1, 9, 0, 5_000, 1_000_000])
    limiter = RedisRateLimiter("redis://unused", client=redis)

    decision = await limiter.check("203.0.113.10", "GET:/health/{service_id}", limit=10, window_seconds=60)
    await limiter.close()

    assert decision.allowed is True
    assert decision.limit == 10
    assert decision.remaining == 9
    assert decision.retry_after_seconds == 0
    assert decision.reset_at == 1005
    assert "203.0.113.10" not in str(redis.eval_calls[0][2])
    assert redis.eval_calls[0][3:] == (10, 60_000)
    assert redis.closed is True


@pytest.mark.asyncio
async def test_redis_rate_limiter_rounds_up_rejected_retry_time() -> None:
    """Verify clients receive whole retry seconds after a rejected request."""
    redis = RedisClientStub([0, 0, 1_250, 60_000, 1_000_000])
    limiter = RedisRateLimiter("redis://unused", client=redis)

    decision = await limiter.check("client", "global", limit=10, window_seconds=60)

    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 2
    assert decision.reset_at == 1060


@pytest.mark.asyncio
async def test_redis_rate_limiter_rejects_invalid_configuration_and_results() -> None:
    """Verify invalid limits and malformed backend responses fail explicitly."""
    limiter = RedisRateLimiter("redis://unused", client=RedisClientStub([1]))

    with pytest.raises(ValueError, match="positive"):
        await limiter.check("client", "global", limit=0, window_seconds=60)

    with pytest.raises(RuntimeError, match="invalid rate limit result"):
        await limiter.check("client", "global", limit=1, window_seconds=60)
