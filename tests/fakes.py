from datetime import datetime, timedelta, timezone

from app.errors import DuplicateServiceError, ServiceNotFoundError
from app.models import HealthCheckResult, ServiceCreate, ServiceRecord, StatusEvent


class FakeEventPublisher:
    def __init__(self) -> None:
        """Create an in-memory event publisher."""
        self.events: list[StatusEvent] = []

    async def publish(self, event: StatusEvent) -> None:
        """Store a published event in memory."""
        self.events.append(event)

    async def ping(self) -> None:
        """Report that the fake publisher is reachable."""
        return None

    async def close(self) -> None:
        """Clear all stored fake events."""
        self.events.clear()


class FakeHealthCache:
    def __init__(self) -> None:
        """Create an in-memory health cache."""
        self._items: dict[str, tuple[HealthCheckResult, datetime]] = {}

    async def get(self, service_id: str) -> HealthCheckResult | None:
        """Return a cached result when it has not expired."""
        item = self._items.get(service_id)
        if item is None:
            return None
        result, expires_at = item
        if expires_at <= datetime.now(timezone.utc):
            self._items.pop(service_id, None)
            return None
        return result.model_copy(update={"cached": True})

    async def set(self, result: HealthCheckResult, ttl_seconds: int) -> None:
        """Store a result until its fake TTL expires."""
        if ttl_seconds <= 0:
            return
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._items[result.service_id] = (result.model_copy(update={"cached": False}), expires_at)

    async def ping(self) -> None:
        """Report that the fake cache is reachable."""
        return None

    async def close(self) -> None:
        """Clear all cached fake results."""
        self._items.clear()


class FakeServiceRepository:
    def __init__(self) -> None:
        """Create an in-memory service repository."""
        self._services: dict[str, ServiceRecord] = {}

    async def init(self) -> None:
        """Report that the fake repository is initialized."""
        return None

    async def create(self, service: ServiceCreate) -> ServiceRecord:
        """Create a fake service record in memory."""
        if any(existing.name == service.name for existing in self._services.values()):
            raise DuplicateServiceError(f"Service with name '{service.name}' already exists")
        record = ServiceRecord(**service.model_dump(mode="json"))
        self._services[record.id] = record
        return record

    async def get(self, service_id: str) -> ServiceRecord:
        """Return a fake service record or raise when missing."""
        try:
            return self._services[service_id]
        except KeyError as exc:
            raise ServiceNotFoundError(f"Service '{service_id}' was not found") from exc

    async def list(self) -> list[ServiceRecord]:
        """List fake service records."""
        return list(self._services.values())

    async def close(self) -> None:
        """Clear all fake service records."""
        self._services.clear()
