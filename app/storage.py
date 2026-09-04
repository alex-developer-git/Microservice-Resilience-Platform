from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.database import create_engine, create_session_factory
from app.db_models import MonitoredService
from app.errors import DuplicateServiceError, ServiceNotFoundError
from app.models import ServiceCreate, ServiceRecord


class ServiceRepository(Protocol):
    async def init(self) -> None:
        """Initialize the repository backend."""
        ...

    async def create(self, service: ServiceCreate) -> ServiceRecord:
        """Persist a new monitored service."""
        ...

    async def get(self, service_id: str) -> ServiceRecord:
        """Return a monitored service by ID."""
        ...

    async def list(self) -> list[ServiceRecord]:
        """Return all monitored services."""
        ...

    async def close(self) -> None:
        """Release repository resources."""
        ...


class PostgresServiceRepository:
    def __init__(self, database_url: str) -> None:
        """Create a PostgreSQL-backed service repository."""
        self._engine: AsyncEngine = create_engine(database_url)
        self._session_factory: async_sessionmaker = create_session_factory(self._engine)

    async def init(self) -> None:
        """Open a database connection to validate availability."""
        async with self._engine.connect():
            return None

    async def create(self, service: ServiceCreate) -> ServiceRecord:
        """Insert a new monitored service record."""
        record = ServiceRecord(**service.model_dump(mode="json"))
        entity = self._to_entity(record)

        async with self._session_factory() as session:
            try:
                session.add(entity)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicateServiceError(f"Service with name '{service.name}' already exists") from exc

        return self._to_record(entity)

    async def get(self, service_id: str) -> ServiceRecord:
        """Load a service record or raise when it is missing."""
        async with self._session_factory() as session:
            entity = await session.get(MonitoredService, service_id)
        if entity is None:
            raise ServiceNotFoundError(f"Service '{service_id}' was not found")
        return self._to_record(entity)

    async def list(self) -> list[ServiceRecord]:
        """List service records ordered by creation time."""
        async with self._session_factory() as session:
            result = await session.execute(select(MonitoredService).order_by(MonitoredService.created_at))
            entities = result.scalars().all()
        return [self._to_record(entity) for entity in entities]

    async def close(self) -> None:
        """Dispose of the SQLAlchemy engine."""
        await self._engine.dispose()

    @staticmethod
    def _to_entity(record: ServiceRecord) -> MonitoredService:
        """Convert a service domain model into an ORM entity."""
        return MonitoredService(
            id=record.id,
            name=record.name,
            url=record.url,
            health_check_path=record.health_check_path,
            timeout_seconds=record.timeout_seconds,
            failure_threshold=record.failure_threshold,
            recovery_timeout_seconds=record.recovery_timeout_seconds,
            cache_ttl_seconds=record.cache_ttl_seconds,
            enabled=record.enabled,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_record(entity: MonitoredService) -> ServiceRecord:
        """Convert an ORM entity into a service domain model."""
        return ServiceRecord(
            id=entity.id,
            name=entity.name,
            url=entity.url,
            health_check_path=entity.health_check_path,
            timeout_seconds=entity.timeout_seconds,
            failure_threshold=entity.failure_threshold,
            recovery_timeout_seconds=entity.recovery_timeout_seconds,
            cache_ttl_seconds=entity.cache_ttl_seconds,
            enabled=entity.enabled,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
