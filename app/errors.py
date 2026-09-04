class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        """Create an application error with a public message."""
        self.message = message
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
