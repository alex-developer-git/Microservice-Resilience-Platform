import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["local", "test", "production"]


class Settings(BaseModel):
    app_name: str = "Microservice Resilience Platform"
    log_level: str = "INFO"
    database_url: str | None = None
    redis_url: str | None = None
    celery_broker_url: str | None = None
    celery_task_name: str = "resilience_platform.process_event"
    environment: Environment = "local"
    otel_enabled: bool = False
    otel_service_name: str = "resilience-platform"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    rate_limit_enabled: bool = True
    rate_limit_fail_open: bool = True
    rate_limit_trust_forwarded_for: bool = False
    rate_limit_global_requests: int = Field(default=120, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    rate_limit_register_service_requests: int = Field(default=10, gt=0)
    rate_limit_health_check_requests: int = Field(default=60, gt=0)
    rate_limit_circuit_breaker_requests: int = Field(default=10, gt=0)


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean setting from an environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_environment() -> Environment:
    """Read and validate the runtime environment name."""
    value = os.getenv("ENVIRONMENT", "local")
    if value == "local":
        return "local"
    if value == "test":
        return "test"
    if value == "production":
        return "production"
    raise ValueError("ENVIRONMENT must be one of: local, test, production")


def _env_positive_int(name: str, default: int) -> int:
    """Read a positive integer setting from an environment variable."""
    raw_value = os.getenv(name)
    value = default if raw_value is None else int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build cached application settings from environment variables."""
    return Settings(
        app_name=os.getenv("APP_NAME", "Microservice Resilience Platform"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database_url=os.getenv("DATABASE_URL") or None,
        redis_url=os.getenv("REDIS_URL") or None,
        celery_broker_url=os.getenv("CELERY_BROKER_URL") or None,
        celery_task_name=os.getenv("CELERY_TASK_NAME", "resilience_platform.process_event"),
        environment=_env_environment(),
        otel_enabled=_env_bool("OTEL_ENABLED"),
        otel_service_name=os.getenv("OTEL_SERVICE_NAME", "resilience-platform"),
        otel_exporter_otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        rate_limit_enabled=_env_bool("RATE_LIMIT_ENABLED", default=True),
        rate_limit_fail_open=_env_bool("RATE_LIMIT_FAIL_OPEN", default=True),
        rate_limit_trust_forwarded_for=_env_bool("RATE_LIMIT_TRUST_FORWARDED_FOR"),
        rate_limit_global_requests=_env_positive_int("RATE_LIMIT_GLOBAL_REQUESTS", 120),
        rate_limit_window_seconds=_env_positive_int("RATE_LIMIT_WINDOW_SECONDS", 60),
        rate_limit_register_service_requests=_env_positive_int("RATE_LIMIT_REGISTER_SERVICE_REQUESTS", 10),
        rate_limit_health_check_requests=_env_positive_int("RATE_LIMIT_HEALTH_CHECK_REQUESTS", 60),
        rate_limit_circuit_breaker_requests=_env_positive_int("RATE_LIMIT_CIRCUIT_BREAKER_REQUESTS", 10),
    )
