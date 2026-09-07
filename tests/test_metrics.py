from datetime import datetime, timezone

from app.metrics import MetricStore
from app.models import CircuitState, HealthCheckResult


def test_autoscaling_probe_metric_is_initialized_at_zero() -> None:
    metrics = MetricStore()

    output = metrics.render_prometheus().decode()

    assert "health_check_probes_total 0.0" in output


def test_metric_store_renders_prometheus_client_metrics() -> None:
    metrics = MetricStore()
    metrics.record_http_request("GET", "/health/{service_id}", 200, 0.123)
    metrics.record_rate_limit_decision("GET:/health/{service_id}", allowed=True)
    metrics.record_rate_limit_decision("GET:/health/{service_id}", allowed=False)
    metrics.record_rate_limit_backend_error("global")
    metrics.record_service_inventory(total=3, enabled=2)
    metrics.record_service_registered()
    metrics.record_manual_trip("svc-1", CircuitState.CLOSED)
    metrics.record_cache_hit("svc-1")
    metrics.record_cache_miss("svc-1")
    metrics.record_health_check_probe()
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

    assert 'http_requests_total{method="GET",path="/health/{service_id}",status_code="200"} 1.0' in output
    assert 'http_request_duration_seconds_count{method="GET",path="/health/{service_id}"} 1.0' in output
    assert 'rate_limit_decisions_total{decision="allowed",scope="GET:/health/{service_id}"} 1.0' in output
    assert 'rate_limit_decisions_total{decision="rejected",scope="GET:/health/{service_id}"} 1.0' in output
    assert 'rate_limit_backend_errors_total{scope="global"} 1.0' in output
    assert "monitored_services 3.0" in output
    assert "enabled_services 2.0" in output
    assert "registered_services_total 1.0" in output
    assert 'health_checks_total{service_id="svc-1",status="healthy"} 1.0' in output
    assert 'health_check_cache_hits_total{service_id="svc-1"} 1.0' in output
    assert 'health_check_cache_misses_total{service_id="svc-1"} 1.0' in output
    assert "health_check_probes_total 1.0" in output
    assert 'health_check_latency_ms{service_id="svc-1"} 42.5' in output
    assert 'health_check_latency_seconds_count{service_id="svc-1"} 1.0' in output
    assert 'service_health_status{service_id="svc-1"} 1.0' in output
    assert 'circuit_breaker_open_total{service_id="svc-1"} 1.0' in output
    assert 'circuit_breaker_transitions_total{from_state="CLOSED",service_id="svc-1",to_state="OPEN"} 1.0' in output
    assert 'circuit_breaker_state{service_id="svc-1"} 0.0' in output
