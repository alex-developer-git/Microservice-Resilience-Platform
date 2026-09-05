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
    assert "registered_services_total 1" in metrics_response.text
    assert "circuit_breaker_manual_trips_total 1" in metrics_response.text


def test_unknown_service_returns_structured_error(api_state: object) -> None:
    """Verify missing services return a structured error."""
    assert isinstance(api_state.repository, FakeServiceRepository)
    app.state.container = api_state
    client = TestClient(app)
    response = client.get("/health/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "service_not_found"
