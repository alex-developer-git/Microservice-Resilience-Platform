from datetime import datetime, timedelta, timezone

from app.errors import CircuitBreakerOpenError
from app.models import CircuitBreakerSnapshot, CircuitState, ServiceRecord


class CircuitBreakerManager:
    def __init__(self) -> None:
        """Create an in-memory circuit breaker state store."""
        self._states: dict[str, CircuitBreakerSnapshot] = {}

    def snapshot(self, service_id: str) -> CircuitBreakerSnapshot:
        """Return the current circuit breaker state for a service."""
        return self._states.get(
            service_id,
            CircuitBreakerSnapshot(service_id=service_id, state=CircuitState.CLOSED),
        )

    def before_request(self, service: ServiceRecord) -> CircuitBreakerSnapshot:
        """Validate that a service can receive a health probe."""
        snapshot = self.snapshot(service.id)
        now = datetime.now(timezone.utc)
        if snapshot.state == CircuitState.OPEN:
            opened_at = snapshot.opened_at or now
            if opened_at + timedelta(seconds=service.recovery_timeout_seconds) <= now:
                snapshot = snapshot.model_copy(update={"state": CircuitState.HALF_OPEN})
                self._states[service.id] = snapshot
                return snapshot
            raise CircuitBreakerOpenError(f"Circuit breaker for service '{service.id}' is open")
        return snapshot

    def record_success(self, service: ServiceRecord) -> CircuitBreakerSnapshot:
        """Reset the circuit breaker after a successful probe."""
        snapshot = CircuitBreakerSnapshot(service_id=service.id, state=CircuitState.CLOSED)
        self._states[service.id] = snapshot
        return snapshot

    def record_failure(self, service: ServiceRecord) -> CircuitBreakerSnapshot:
        """Record a failed probe and open the circuit when needed."""
        current = self.snapshot(service.id)
        now = datetime.now(timezone.utc)
        failure_count = current.failure_count + 1
        state = current.state
        opened_at = current.opened_at

        if current.state == CircuitState.HALF_OPEN or failure_count >= service.failure_threshold:
            state = CircuitState.OPEN
            opened_at = now

        snapshot = CircuitBreakerSnapshot(
            service_id=service.id,
            state=state,
            failure_count=failure_count,
            last_failure_at=now,
            opened_at=opened_at,
        )
        self._states[service.id] = snapshot
        return snapshot

    def trip(self, service_id: str) -> CircuitBreakerSnapshot:
        """Manually force a service circuit breaker open."""
        now = datetime.now(timezone.utc)
        snapshot = CircuitBreakerSnapshot(
            service_id=service_id,
            state=CircuitState.OPEN,
            failure_count=0,
            opened_at=now,
            last_failure_at=now,
        )
        self._states[service_id] = snapshot
        return snapshot
