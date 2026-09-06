from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.models import CircuitState, HealthCheckResult


class MetricStore:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Create Prometheus metrics for service monitoring."""
        self._registry = registry or CollectorRegistry()
        self._http_requests = Counter(
            "http_requests",
            "Number of HTTP requests by method, route, and status code.",
            ["method", "path", "status_code"],
            registry=self._registry,
        )
        self._http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration distribution in seconds.",
            ["method", "path"],
            registry=self._registry,
        )
        self._service_registered = Counter(
            "registered_services",
            "Number of registered services.",
            registry=self._registry,
        )
        self._monitored_services = Gauge(
            "monitored_services",
            "Current number of monitored services.",
            registry=self._registry,
        )
        self._enabled_services = Gauge(
            "enabled_services",
            "Current number of enabled monitored services.",
            registry=self._registry,
        )
        self._manual_trips = Counter(
            "circuit_breaker_manual_trips",
            "Number of manual circuit breaker trips.",
            registry=self._registry,
        )
        self._circuit_breaker_open_total = Counter(
            "circuit_breaker_open",
            "Number of times a service circuit breaker entered OPEN state.",
            ["service_id"],
            registry=self._registry,
        )
        self._circuit_breaker_transitions = Counter(
            "circuit_breaker_transitions",
            "Number of circuit breaker state transitions.",
            ["service_id", "from_state", "to_state"],
            registry=self._registry,
        )
        self._cache_hits = Counter(
            "health_check_cache_hits",
            "Number of health check cache hits.",
            ["service_id"],
            registry=self._registry,
        )
        self._cache_misses = Counter(
            "health_check_cache_misses",
            "Number of health check cache misses.",
            ["service_id"],
            registry=self._registry,
        )
        self._health_check_probes = Counter(
            "health_check_probes",
            "Number of uncached outbound health check probes started.",
            registry=self._registry,
        )
        self._health_checks = Counter(
            "health_checks",
            "Number of health checks by service and status.",
            ["service_id", "status"],
            registry=self._registry,
        )
        self._service_health_status = Gauge(
            "service_health_status",
            "Latest service health status. Healthy=1, unhealthy=0.",
            ["service_id"],
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

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        """Record HTTP request count and latency."""
        self._http_requests.labels(method=method, path=path, status_code=str(status_code)).inc()
        self._http_request_duration_seconds.labels(method=method, path=path).observe(duration_seconds)

    def record_service_inventory(self, total: int, enabled: int) -> None:
        """Record current service inventory gauges."""
        self._monitored_services.set(total)
        self._enabled_services.set(enabled)

    def record_service_registered(self) -> None:
        """Increment the service registration counter."""
        self._service_registered.inc()

    def record_manual_trip(self, service_id: str, previous_state: CircuitState = CircuitState.CLOSED) -> None:
        """Record a manual circuit breaker trip."""
        self._manual_trips.inc()
        self.record_circuit_transition(service_id, previous_state, CircuitState.OPEN)
        self._record_circuit_state(service_id, CircuitState.OPEN)

    def record_cache_hit(self, service_id: str) -> None:
        """Record a health check cache hit."""
        self._cache_hits.labels(service_id=service_id).inc()

    def record_cache_miss(self, service_id: str) -> None:
        """Record a health check cache miss."""
        self._cache_misses.labels(service_id=service_id).inc()

    def record_health_check_probe(self) -> None:
        """Increment the per-pod probe counter used for autoscaling."""
        self._health_check_probes.inc()

    def record_health_check(self, result: HealthCheckResult) -> None:
        """Record health check counters, latency, and circuit state."""
        status = "healthy" if result.healthy else "unhealthy"
        self._health_checks.labels(service_id=result.service_id, status=status).inc()
        self._service_health_status.labels(service_id=result.service_id).set(1 if result.healthy else 0)
        if result.latency_ms is not None:
            self._latest_latency_ms.labels(service_id=result.service_id).set(result.latency_ms)
            self._latency_seconds.labels(service_id=result.service_id).observe(result.latency_ms / 1000)
        self._record_circuit_state(result.service_id, result.circuit_state)

    def record_circuit_transition(
        self,
        service_id: str,
        from_state: CircuitState,
        to_state: CircuitState,
    ) -> None:
        """Record circuit breaker transitions and OPEN entries."""
        if from_state == to_state:
            return
        self._circuit_breaker_transitions.labels(
            service_id=service_id,
            from_state=from_state.value,
            to_state=to_state.value,
        ).inc()
        if to_state == CircuitState.OPEN:
            self._circuit_breaker_open_total.labels(service_id=service_id).inc()

    def render_prometheus(self) -> bytes:
        """Render all metrics in Prometheus exposition format."""
        return generate_latest(self._registry)

    def _record_circuit_state(self, service_id: str, state: CircuitState) -> None:
        """Store the numeric representation of a circuit state."""
        state_values = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}
        self._circuit_state.labels(service_id=service_id).set(state_values[state])
