from fastapi.testclient import TestClient

from app.main import app
from tests.fakes import FakeServiceRepository


def test_container_health_endpoint() -> None:
    """Verify the container health endpoint response."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Correlation-ID"]


def test_container_health_endpoint_preserves_correlation_id() -> None:
    """Verify caller-provided correlation IDs are returned for tracing."""
    client = TestClient(app)

    response = client.get("/health", headers={"X-Correlation-ID": "trace-123"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "trace-123"


def test_container_health_endpoint_replaces_invalid_correlation_id() -> None:
    """Verify invalid caller-provided correlation IDs are replaced."""
    client = TestClient(app)

    response = client.get("/health", headers={"X-Correlation-ID": "invalid id"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] != "invalid id"


def test_readiness_endpoint_checks_dependencies(api_state: object) -> None:
    """Verify readiness reports all dependency checks."""
    app.state.container = api_state
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["postgres"]["status"] == "ok"
    assert response.json()["checks"]["redis"]["status"] == "ok"
    assert response.json()["checks"]["celery_broker"]["status"] == "ok"


def test_register_service_and_metrics(api_state: object) -> None:
    """Verify service registration, circuit trip, and metrics output."""
    app.state.container = api_state
    client = TestClient(app)
    response = client.post(
        "/register-service",
        json={"name": "orders", "url": "https://orders.example.com", "health_check_path": "/healthz"},
    )
    assert response.status_code == 201
    service_id = response.json()["id"]

    trip_response = client.post(f"/circuit-breaker/{service_id}/trip")
    assert trip_response.status_code == 200
    assert trip_response.json()["state"] == "OPEN"

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert 'http_requests_total{method="POST",path="/register-service",status_code="201"} 1.0' in metrics_response.text
    assert "registered_services_total 1" in metrics_response.text
    assert "monitored_services 1" in metrics_response.text
    assert "enabled_services 1" in metrics_response.text
    assert "circuit_breaker_manual_trips_total 1" in metrics_response.text


def test_alertmanager_webhook_broadcasts_alert(api_state: object) -> None:
    """Verify Alertmanager webhook payloads are forwarded to status clients."""

    class BroadcastRecorder:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def broadcast(self, payload: dict[str, object]) -> None:
            self.payloads.append(payload)

    broadcaster = BroadcastRecorder()
    api_state.websocket_manager = broadcaster
    app.state.container = api_state
    client = TestClient(app)

    response = client.post(
        "/alerts/alertmanager",
        json={
            "receiver": "resilience-platform-webhook",
            "groupKey": '{}:{alertname="CircuitBreakerOpen", service_id="svc-1"}',
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "CircuitBreakerOpen",
                        "service_id": "svc-1",
                        "severity": "critical",
                    },
                    "annotations": {
                        "summary": "Circuit breaker is open for service svc-1",
                    },
                    "startsAt": "2026-09-06T12:00:00Z",
                    "fingerprint": "abc123",
                }
            ],
        },
    )

    assert response.status_code == 202
    assert response.json() == {"received": 1, "forwarded": 1}
    assert broadcaster.payloads[0]["event_type"] == "alertmanager_alert"
    assert broadcaster.payloads[0]["service_id"] == "svc-1"
    assert broadcaster.payloads[0]["payload"]["labels"]["alertname"] == "CircuitBreakerOpen"


def test_unknown_service_returns_structured_error(api_state: object) -> None:
    """Verify missing services return a structured error."""
    assert isinstance(api_state.repository, FakeServiceRepository)
    app.state.container = api_state
    client = TestClient(app)
    response = client.get("/health/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "service_not_found"
