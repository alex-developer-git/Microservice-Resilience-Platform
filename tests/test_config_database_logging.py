import json
import logging

import pytest

from app import database
from app.config import _env_bool, _env_environment, _env_positive_int, get_settings
from app.logging_config import JsonFormatter, configure_logging, log_extra


def test_environment_helpers_parse_expected_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment helper parsing and validation."""
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    assert _env_bool("OTEL_ENABLED", default=True) is True

    monkeypatch.setenv("OTEL_ENABLED", "yes")
    assert _env_bool("OTEL_ENABLED") is True

    monkeypatch.setenv("OTEL_ENABLED", "off")
    assert _env_bool("OTEL_ENABLED") is False

    monkeypatch.setenv("ENVIRONMENT", "test")
    assert _env_environment() == "test"

    monkeypatch.setenv("ENVIRONMENT", "invalid")
    with pytest.raises(ValueError):
        _env_environment()


def test_get_settings_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings are loaded from environment variables."""
    get_settings.cache_clear()
    monkeypatch.setenv("APP_NAME", "CI App")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@postgres/app")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "pyamqp://guest:guest@rabbitmq:5672//")
    monkeypatch.setenv("CELERY_TASK_NAME", "custom.task")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4317")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_FAIL_OPEN", "false")
    monkeypatch.setenv("RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    monkeypatch.setenv("RATE_LIMIT_GLOBAL_REQUESTS", "90")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("RATE_LIMIT_REGISTER_SERVICE_REQUESTS", "8")
    monkeypatch.setenv("RATE_LIMIT_HEALTH_CHECK_REQUESTS", "45")
    monkeypatch.setenv("RATE_LIMIT_CIRCUIT_BREAKER_REQUESTS", "6")

    settings = get_settings()
    get_settings.cache_clear()

    assert settings.app_name == "CI App"
    assert settings.log_level == "debug"
    assert settings.database_url == "postgresql://user:pass@postgres/app"
    assert settings.redis_url == "redis://redis:6379/0"
    assert settings.celery_broker_url == "pyamqp://guest:guest@rabbitmq:5672//"
    assert settings.celery_task_name == "custom.task"
    assert settings.environment == "production"
    assert settings.otel_enabled is True
    assert settings.otel_service_name == "svc"
    assert settings.otel_exporter_otlp_endpoint == "http://otel:4317"
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_fail_open is False
    assert settings.rate_limit_trust_forwarded_for is True
    assert settings.rate_limit_global_requests == 90
    assert settings.rate_limit_window_seconds == 30
    assert settings.rate_limit_register_service_requests == 8
    assert settings.rate_limit_health_check_requests == 45
    assert settings.rate_limit_circuit_breaker_requests == 6


def test_positive_integer_environment_helper_rejects_invalid_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify rate limit values cannot be zero, negative, or non-numeric."""
    monkeypatch.delenv("RATE_LIMIT_TEST", raising=False)
    assert _env_positive_int("RATE_LIMIT_TEST", 12) == 12

    monkeypatch.setenv("RATE_LIMIT_TEST", "0")
    with pytest.raises(ValueError, match="positive integer"):
        _env_positive_int("RATE_LIMIT_TEST", 12)

    monkeypatch.setenv("RATE_LIMIT_TEST", "invalid")
    with pytest.raises(ValueError):
        _env_positive_int("RATE_LIMIT_TEST", 12)


def test_database_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify database URL normalization and engine creation."""
    fake_engine = object()
    instrumented: list[object] = []

    def fake_create_async_engine(database_url: str, *, pool_pre_ping: bool) -> object:
        """Return a fake SQLAlchemy engine."""
        assert database_url == "postgresql+asyncpg://user:pass@postgres/app"
        assert pool_pre_ping is True
        return fake_engine

    monkeypatch.setattr(database, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(database, "instrument_sqlalchemy_engine", instrumented.append)

    assert database.normalize_database_url("postgresql+asyncpg://db") == "postgresql+asyncpg://db"
    assert database.normalize_database_url("postgresql://db") == "postgresql+asyncpg://db"
    assert database.normalize_database_url("sqlite:///db.sqlite") == "sqlite:///db.sqlite"
    assert database.create_engine("postgresql://user:pass@postgres/app") is fake_engine
    assert instrumented == [fake_engine]


def test_json_logging_formatter_includes_structured_fields() -> None:
    """Verify structured log fields are emitted as JSON."""
    formatter = JsonFormatter()
    record = logging.LogRecord("app.test", logging.INFO, __file__, 10, "hello %s", ("world",), None)
    record.__dict__.update(log_extra(message="structured", service_id="svc-1"))

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello world"
    assert payload["extra_message"] == "structured"
    assert payload["service_id"] == "svc-1"


def test_configure_logging_replaces_root_handlers() -> None:
    """Verify root logging is configured with the JSON formatter."""
    configure_logging("warning")

    root = logging.getLogger()

    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
