from datetime import datetime, timedelta, timezone

import pytest

from app.circuit_breaker import CircuitBreakerManager
from app.errors import CircuitBreakerOpenError
from app.models import CircuitState, ServiceCreate, ServiceRecord


def make_service(**overrides: object) -> ServiceRecord:
    """Build a service record for circuit breaker tests."""
    data = {
        "name": "orders",
        "url": "https://orders.example.com",
        "failure_threshold": 2,
        "recovery_timeout_seconds": 5,
    }
    data.update(overrides)
    return ServiceRecord(**ServiceCreate(**data).model_dump(mode="json"))


def test_circuit_breaker_opens_after_failure_threshold() -> None:
    """Verify failures open the circuit at the configured threshold."""
    service = make_service()
    manager = CircuitBreakerManager()

    assert manager.record_failure(service).state == CircuitState.CLOSED
    snapshot = manager.record_failure(service)

    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == 2


def test_open_circuit_blocks_requests_until_recovery_timeout() -> None:
    """Verify an open circuit rejects requests before recovery."""
    service = make_service()
    manager = CircuitBreakerManager()
    manager.trip(service.id)

    with pytest.raises(CircuitBreakerOpenError):
        manager.before_request(service)


def test_open_circuit_moves_to_half_open_after_timeout() -> None:
    """Verify an open circuit becomes half-open after recovery."""
    service = make_service()
    manager = CircuitBreakerManager()
    manager.trip(service.id)
    current = manager.snapshot(service.id)
    manager._states[service.id] = current.model_copy(
        update={"opened_at": datetime.now(timezone.utc) - timedelta(seconds=6)}
    )

    snapshot = manager.before_request(service)

    assert snapshot.state == CircuitState.HALF_OPEN
