import os
from uuid import uuid4

import pytest

from alembic import command
from alembic.config import Config
from app.database import normalize_database_url
from app.models import ServiceCreate
from app.storage import PostgresServiceRepository


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_repository_persists_service() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    os.environ["DATABASE_URL"] = normalize_database_url(database_url)
    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    repository = PostgresServiceRepository(database_url)
    await repository.init()
    try:
        service_name = f"integration-orders-{uuid4()}"
        created = await repository.create(ServiceCreate(name=service_name, url="https://orders.example.com"))
        loaded = await repository.get(created.id)
    finally:
        await repository.close()

    assert loaded.id == created.id
    assert loaded.name == service_name
