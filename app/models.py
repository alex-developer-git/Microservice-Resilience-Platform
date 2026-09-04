from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from app.url_security import UnsafeUrlError, validate_public_http_url


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: AnyHttpUrl
    health_check_path: str = Field(default="/health", min_length=1, max_length=256)
    timeout_seconds: float = Field(default=3.0, ge=0.1, le=60.0)
    failure_threshold: int = Field(default=3, ge=1, le=100)
    recovery_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    cache_ttl_seconds: int = Field(default=10, ge=0, le=3600)
    enabled: bool = True

    @field_validator("health_check_path")
    @classmethod
    def normalize_health_path(cls, value: str) -> str:
        """Ensure health check paths stay relative to the service URL host."""
        stripped = value.strip()
        if "://" in stripped or stripped.startswith("//") or "\\" in stripped:
            raise ValueError("health_check_path must be a relative URL path")
        return stripped if stripped.startswith("/") else f"/{stripped}"

    @field_validator("url")
    @classmethod
    def validate_service_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Reject service URLs that are unsafe for outbound health checks."""
        try:
            validate_public_http_url(str(value))
        except UnsafeUrlError as exc:
            raise ValueError(str(exc)) from exc
        return value


class ServiceRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=120)
    url: str
    health_check_path: str = Field(default="/health", min_length=1, max_length=256)
    timeout_seconds: float = Field(default=3.0, ge=0.1, le=60.0)
    failure_threshold: int = Field(default=3, ge=1, le=100)
    recovery_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    cache_ttl_seconds: int = Field(default=10, ge=0, le=3600)
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator("health_check_path")
    @classmethod
    def normalize_health_path(cls, value: str) -> str:
        """Ensure stored health check paths stay relative to the service URL host."""
        stripped = value.strip()
        if "://" in stripped or stripped.startswith("//") or "\\" in stripped:
            raise ValueError("health_check_path must be a relative URL path")
        return stripped if stripped.startswith("/") else f"/{stripped}"


class ServiceResponse(BaseModel):
    id: str
    name: str
    url: str
    health_check_path: str
    timeout_seconds: float
    failure_threshold: int
    recovery_timeout_seconds: int
    cache_ttl_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CircuitBreakerSnapshot(BaseModel):
    service_id: str
    state: CircuitState
    failure_count: int = 0
    last_failure_at: datetime | None = None
    opened_at: datetime | None = None


class HealthCheckResult(BaseModel):
    service_id: str
    service_name: str
    checked_at: datetime
    healthy: bool
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None
    circuit_state: CircuitState
    cached: bool = False


class StatusEvent(BaseModel):
    event_type: str
    service_id: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
