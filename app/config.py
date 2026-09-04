import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

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
    )
