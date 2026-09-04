import asyncio
import logging
from typing import Any, Protocol

from app.logging_config import log_extra
from app.models import StatusEvent

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish(self, event: StatusEvent) -> None:
        """Publish a status event to an external backend."""
        ...

    async def ping(self) -> None:
        """Verify that the event backend is reachable."""
        ...

    async def close(self) -> None:
        """Close event backend resources."""
        ...


class EventBroadcaster(Protocol):
    async def broadcast(self, payload: dict[str, object]) -> None:
        """Broadcast a payload to connected clients."""
        ...


class CeleryEventPublisher:
    def __init__(self, broker_url: str, task_name: str) -> None:
        """Create a Celery publisher for status events."""
        from celery import Celery

        self._task_name = task_name
        self._celery: Any = Celery("resilience_platform", broker=broker_url)

    async def publish(self, event: StatusEvent) -> None:
        """Send a status event as a Celery task."""
        payload = event.model_dump(mode="json")
        await asyncio.to_thread(self._celery.send_task, self._task_name, kwargs={"event": payload})
        logger.info(
            "event_published_to_celery",
            extra=log_extra(event_type=event.event_type, service_id=event.service_id),
        )

    async def ping(self) -> None:
        """Check that Celery can connect to the broker."""
        await asyncio.to_thread(self._ping_broker)

    def _ping_broker(self) -> None:
        """Open a broker connection to verify availability."""
        with self._celery.connection_for_write() as connection:
            connection.ensure_connection(max_retries=1)

    async def close(self) -> None:
        """Close publisher resources when present."""
        return None


class RealtimeEventPublisher:
    def __init__(self, publisher: EventPublisher, broadcaster: EventBroadcaster) -> None:
        """Combine backend publishing with local realtime broadcasting."""
        self._publisher = publisher
        self._broadcaster = broadcaster

    async def publish(self, event: StatusEvent) -> None:
        """Publish an event and broadcast it to WebSocket clients."""
        await self._publisher.publish(event)
        await self._broadcaster.broadcast(event.model_dump(mode="json"))

    async def ping(self) -> None:
        """Check the underlying event publisher health."""
        await self._publisher.ping()

    async def close(self) -> None:
        """Close the underlying event publisher."""
        await self._publisher.close()
