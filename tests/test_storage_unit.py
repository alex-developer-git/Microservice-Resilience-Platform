import pytest

from app import storage
from app.models import ServiceCreate, ServiceRecord
from app.storage import PostgresServiceRepository


class FakeConnection:
    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.connected = False
        self.disposed = False

    def connect(self) -> FakeConnection:
        self.connected = True
        return FakeConnection()

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_postgres_repository_init_close_and_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = FakeEngine()
    monkeypatch.setattr(storage, "create_engine", lambda database_url: fake_engine)
    monkeypatch.setattr(storage, "create_session_factory", lambda engine: object())

    repository = PostgresServiceRepository("postgresql://postgres/app")
    await repository.init()

    record = ServiceRecord(**ServiceCreate(name="orders", url="https://orders.example.com").model_dump(mode="json"))
    entity = PostgresServiceRepository._to_entity(record)
    mapped = PostgresServiceRepository._to_record(entity)

    await repository.close()

    assert fake_engine.connected is True
    assert fake_engine.disposed is True
    assert mapped == record
