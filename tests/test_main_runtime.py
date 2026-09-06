from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.main import AppState, _record_service_inventory, build_state, lifespan
from tests.fakes import FakeEventPublisher, FakeHealthCache, FakeServiceRepository


def test_build_state_requires_runtime_dependencies() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        build_state(Settings())

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        build_state(Settings(database_url="postgresql://db"))

    with pytest.raises(RuntimeError, match="CELERY_BROKER_URL"):
        build_state(Settings(database_url="postgresql://db", redis_url="redis://redis"))


def test_build_state_wires_runtime_components(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class Repository(FakeServiceRepository):
        def __init__(self, database_url: str) -> None:
            super().__init__()
            created["database_url"] = database_url

    class Cache(FakeHealthCache):
        def __init__(self, redis_url: str) -> None:
            super().__init__()
            created["redis_url"] = redis_url

    class Publisher(FakeEventPublisher):
        def __init__(self, broker_url: str, task_name: str) -> None:
            super().__init__()
            created["broker_url"] = broker_url
            created["task_name"] = task_name

    monkeypatch.setattr("app.main.PostgresServiceRepository", Repository)
    monkeypatch.setattr("app.main.RedisHealthCache", Cache)
    monkeypatch.setattr("app.main.CeleryEventPublisher", Publisher)

    state = build_state(
        Settings(
            database_url="postgresql://postgres/app",
            redis_url="redis://redis:6379/0",
            celery_broker_url="pyamqp://guest:guest@rabbitmq:5672//",
            celery_task_name="events.process",
        )
    )

    assert isinstance(state, AppState)
    assert created == {
        "database_url": "postgresql://postgres/app",
        "redis_url": "redis://redis:6379/0",
        "broker_url": "pyamqp://guest:guest@rabbitmq:5672//",
        "task_name": "events.process",
    }


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    state = AppState(
        repository=FakeServiceRepository(),
        cache=FakeHealthCache(),
        events=FakeEventPublisher(),
        circuit_breakers=SimpleNamespace(),
        metrics=SimpleNamespace(),
        websocket_manager=SimpleNamespace(),
        http_client=httpx.AsyncClient(),
    )

    async def init_repository() -> None:
        calls.append("repository.init")

    async def close_events() -> None:
        calls.append("events.close")

    async def close_http_client() -> None:
        calls.append("http_client.close")

    async def close_cache() -> None:
        calls.append("cache.close")

    async def close_repository() -> None:
        calls.append("repository.close")

    state.repository.init = init_repository
    state.events.close = close_events
    state.http_client.aclose = close_http_client
    state.cache.close = close_cache
    state.repository.close = close_repository

    app = SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(environment="test"))
    monkeypatch.setattr("app.main.configure_logging", lambda level: calls.append(f"logging.{level}"))
    monkeypatch.setattr("app.main.build_state", lambda settings: state)

    async with lifespan(app):
        assert app.state.container is state

    assert calls == [
        "logging.INFO",
        "repository.init",
        "events.close",
        "http_client.close",
        "cache.close",
        "repository.close",
    ]


@pytest.mark.asyncio
async def test_record_service_inventory_does_not_fail_startup_when_repository_list_fails() -> None:
    class Repository(FakeServiceRepository):
        async def list(self) -> list[object]:
            raise RuntimeError("services table is not ready")

    class Metrics:
        def __init__(self) -> None:
            self.recorded = False

        def record_service_inventory(self, total: int, enabled: int) -> None:
            self.recorded = True

    metrics = Metrics()
    state = AppState(
        repository=Repository(),
        cache=FakeHealthCache(),
        events=FakeEventPublisher(),
        circuit_breakers=SimpleNamespace(),
        metrics=metrics,
        websocket_manager=SimpleNamespace(),
        http_client=httpx.AsyncClient(),
    )

    await _record_service_inventory(state)
    await state.http_client.aclose()

    assert metrics.recorded is False
