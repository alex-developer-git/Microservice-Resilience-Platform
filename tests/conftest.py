from collections.abc import AsyncIterator

import httpx
import pytest

from app.circuit_breaker import CircuitBreakerManager
from app.health import HealthChecker
from app.main import AppState
from app.metrics import MetricStore
from app.websocket import WebSocketStatusManager
from tests.fakes import FakeEventPublisher, FakeHealthCache, FakeServiceRepository


async def allow_health_check_target(_: str) -> None:
    """Allow outbound targets in tests that mock the HTTP client."""
    return None


@pytest.fixture
async def repository() -> AsyncIterator[FakeServiceRepository]:
    """Provide an initialized fake service repository."""
    repo = FakeServiceRepository()
    await repo.init()
    yield repo
    await repo.close()


@pytest.fixture
async def cache() -> AsyncIterator[FakeHealthCache]:
    """Provide an in-memory fake health cache."""
    health_cache = FakeHealthCache()
    yield health_cache
    await health_cache.close()


@pytest.fixture
def events() -> FakeEventPublisher:
    """Provide a fake event publisher."""
    return FakeEventPublisher()


@pytest.fixture
def metrics() -> MetricStore:
    """Provide an isolated Prometheus metric store."""
    return MetricStore()


@pytest.fixture
def circuit_breakers() -> CircuitBreakerManager:
    """Provide a fresh circuit breaker manager."""
    return CircuitBreakerManager()


@pytest.fixture
def health_checker(
    repository: FakeServiceRepository,
    cache: FakeHealthCache,
    circuit_breakers: CircuitBreakerManager,
    events: FakeEventPublisher,
    metrics: MetricStore,
) -> HealthChecker:
    """Provide a health checker wired to fake dependencies."""
    return HealthChecker(
        repository,
        cache,
        circuit_breakers,
        events,
        metrics,
        httpx.AsyncClient(),
        target_validator=allow_health_check_target,
    )


@pytest.fixture
def api_state() -> AppState:
    """Provide a FastAPI app state with fake dependencies."""
    return AppState(
        repository=FakeServiceRepository(),
        cache=FakeHealthCache(),
        events=FakeEventPublisher(),
        circuit_breakers=CircuitBreakerManager(),
        metrics=MetricStore(),
        websocket_manager=WebSocketStatusManager(),
        http_client=httpx.AsyncClient(),
    )
