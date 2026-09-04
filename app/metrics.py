from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.models import CircuitState, HealthCheckResult


class MetricStore:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Create Prometheus metrics for service monitoring."""
        self._registry = registry or CollectorRegistry()
        self._service_registered = Counter(
            "registered_services",
            "Number of registered services.",
            registry=self._registry,
        )
        self._manual_trips = Counter(
            "circuit_breaker_manual_trips",
            "Number of manual circuit breaker trips.",
            registry=self._registry,
        )
        self._health_checks = Counter(
            "health_checks",
            "Number of health checks by service and status.",
            ["service_id", "status"],
            registry=self._registry,
        )
        self._latest_latency_ms = Gauge(
            "health_check_latency_ms",
            "Last observed health check latency in milliseconds.",
            ["service_id"],
            registry=self._registry,
        )
        self._latency_seconds = Histogram(
            "health_check_latency_seconds",
            "Health check latency distribution in seconds.",
            ["service_id"],
            registry=self._registry,
        )
        self._circuit_state = Gauge(
            "circuit_breaker_state",
            "Current circuit breaker state. CLOSED=0, HALF_OPEN=1, OPEN=2.",
            ["service_id"],
            registry=self._registry,
        )

    def record_service_registered(self) -> None:
        """Increment the service registration counter."""
        self._service_registered.inc()

    def record_manual_trip(self, service_id: str) -> None:
        """Record a manual circuit breaker trip."""
        self._manual_trips.inc()
        self._record_circuit_state(service_id, CircuitState.OPEN)

    def record_health_check(self, result: HealthCheckResult) -> None:
        """Record health check counters, latency, and circuit state."""
        status = "healthy" if result.healthy else "unhealthy"
        self._health_checks.labels(service_id=result.service_id, status=status).inc()
        if result.latency_ms is not None:
            self._latest_latency_ms.labels(service_id=result.service_id).set(result.latency_ms)
            self._latency_seconds.labels(service_id=result.service_id).observe(result.latency_ms / 1000)
        self._record_circuit_state(result.service_id, result.circuit_state)

    def render_prometheus(self) -> bytes:
        """Render all metrics in Prometheus exposition format."""
        return generate_latest(self._registry)

    def _record_circuit_state(self, service_id: str, state: CircuitState) -> None:
        """Store the numeric representation of a circuit state."""
        state_values = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}
        self._circuit_state.labels(service_id=service_id).set(state_values[state])
