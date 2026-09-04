import sys
import types

import pytest

from app.events import CeleryEventPublisher, RealtimeEventPublisher
from app.models import StatusEvent


class FakeConnection:
    def __init__(self) -> None:
        """Create a fake broker connection."""
        self.max_retries: int | None = None

    def __enter__(self) -> "FakeConnection":
        """Enter the fake broker connection context."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Exit the fake broker connection context."""
        return None

    def ensure_connection(self, *, max_retries: int) -> None:
        """Record the requested connection retry count."""
        self.max_retries = max_retries


class FakeCelery:
    instances: list["FakeCelery"] = []

    def __init__(self, name: str, *, broker: str) -> None:
        """Create a fake Celery app."""
        self.name = name
        self.broker = broker
        self.sent_tasks: list[tuple[str, dict[str, object]]] = []
        self.connection = FakeConnection()
        FakeCelery.instances.append(self)

    def send_task(self, task_name: str, *, kwargs: dict[str, object]) -> None:
        """Record a fake Celery task send."""
        self.sent_tasks.append((task_name, kwargs))

    def connection_for_write(self) -> FakeConnection:
        """Return the fake broker write connection."""
        return self.connection


class FakeBroadcaster:
    def __init__(self) -> None:
        """Create an in-memory broadcaster."""
        self.payloads: list[dict[str, object]] = []

    async def broadcast(self, payload: dict[str, object]) -> None:
        """Record a broadcast payload."""
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_celery_event_publisher_sends_and_pings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Celery event publishing and broker pinging."""
    FakeCelery.instances.clear()
    monkeypatch.setitem(sys.modules, "celery", types.SimpleNamespace(Celery=FakeCelery))
    event = StatusEvent(event_type="service_registered", service_id="svc-1", payload={"name": "orders"})

    publisher = CeleryEventPublisher("pyamqp://guest:guest@rabbitmq:5672//", "resilience.task")
    await publisher.publish(event)
    await publisher.ping()
    await publisher.close()

    celery = FakeCelery.instances[0]
    assert celery.name == "resilience_platform"
    assert celery.broker == "pyamqp://guest:guest@rabbitmq:5672//"
    task_name, kwargs = celery.sent_tasks[0]
    assert task_name == "resilience.task"
    assert kwargs["event"]["event_type"] == "service_registered"
    assert kwargs["event"]["service_id"] == "svc-1"
    assert kwargs["event"]["payload"] == {"name": "orders"}
    assert "created_at" in kwargs["event"]
    assert celery.connection.max_retries == 1


@pytest.mark.asyncio
async def test_realtime_event_publisher_delegates_and_broadcasts() -> None:
    """Verify realtime publishing delegates and broadcasts."""
    publisher = CeleryEventPublisher.__new__(CeleryEventPublisher)
    publisher.published: list[StatusEvent] = []
    publisher.closed = False
    broadcaster = FakeBroadcaster()
    event = StatusEvent(event_type="health_checked", service_id="svc-1", payload={"healthy": True})

    async def publish(status_event: StatusEvent) -> None:
        """Record a delegated status event."""
        publisher.published.append(status_event)

    async def ping() -> None:
        """Record a delegated ping."""
        publisher.pinged = True

    async def close() -> None:
        """Record a delegated close."""
        publisher.closed = True

    publisher.publish = publish
    publisher.ping = ping
    publisher.close = close

    realtime = RealtimeEventPublisher(publisher, broadcaster)
    await realtime.publish(event)
    await realtime.ping()
    await realtime.close()

    assert publisher.published == [event]
    assert publisher.pinged is True
    assert publisher.closed is True
    assert broadcaster.payloads == [event.model_dump(mode="json")]
