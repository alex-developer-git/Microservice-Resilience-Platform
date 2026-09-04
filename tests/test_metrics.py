from datetime import datetime, timezone

from app.metrics import MetricStore
from app.models import CircuitState, HealthCheckResult


def test_metric_store_renders_prometheus_client_metrics() -> None:
    metrics = MetricStore()
    metrics.record_service_registered()
    metrics.record_manual_trip("svc-1")
    metrics.record_health_check(
        HealthCheckResult(
            service_id="svc-1",
            service_name="orders",
            checked_at=datetime.now(timezone.utc),
            healthy=True,
            status_code=200,
            latency_ms=42.5,
            circuit_state=CircuitState.CLOSED,
        )
    )

    output = metrics.render_prometheus().decode()

    assert "registered_services_total 1.0" in output
    assert 'health_checks_total{service_id="svc-1",status="healthy"} 1.0' in output
    assert 'health_check_latency_ms{service_id="svc-1"} 42.5' in output
    assert 'health_check_latency_seconds_count{service_id="svc-1"} 1.0' in output
    assert 'circuit_breaker_state{service_id="svc-1"} 0.0' in output
