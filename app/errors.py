from collections.abc import Mapping


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, headers: Mapping[str, str] | None = None) -> None:
        """Create an application error with a public message."""
        self.message = message
        self.headers = dict(headers or {})
        super().__init__(message)


class ServiceNotFoundError(AppError):
    status_code: int = 404
    code: str = "service_not_found"


class DuplicateServiceError(AppError):
    status_code: int = 409
    code: str = "duplicate_service"


class CircuitBreakerOpenError(AppError):
    status_code: int = 503
    code: str = "circuit_breaker_open"


class RateLimitExceededError(AppError):
    status_code: int = 429
    code: str = "rate_limit_exceeded"

    def __init__(self, *, limit: int, remaining: int, reset_at: int, retry_after_seconds: int) -> None:
        """Create a rate limit response with retry metadata."""
        super().__init__(
            "Too many requests",
            headers={
                "Retry-After": str(retry_after_seconds),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_at),
            },
        )


class RateLimitBackendUnavailableError(AppError):
    status_code: int = 503
    code: str = "rate_limit_backend_unavailable"
