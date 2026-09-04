from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.health import HealthChecker
from app.models import CircuitState, ServiceCreate
from tests.fakes import FakeServiceRepository


@pytest.mark.asyncio
async def test_health_check_records_success(
    repository: FakeServiceRepository,
    health_checker: HealthChecker,
) -> None:
    service = await repository.create(ServiceCreate(name="billing", url="https://billing.example.com"))

    health_checker._send_health_request = AsyncMock(return_value=httpx.Response(200))

    result = await health_checker.check(service.id, use_cache=False)

    assert result.healthy is True
    assert result.status_code == 200
    assert result.circuit_state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_health_check_uses_cached_result(
    repository: FakeServiceRepository,
    health_checker: HealthChecker,
) -> None:
    service = await repository.create(ServiceCreate(name="catalog", url="https://catalog.example.com"))

    health_checker._send_health_request = AsyncMock(return_value=httpx.Response(200))

    first = await health_checker.check(service.id)
    second = await health_checker.check(service.id)

    assert first.cached is False
    assert second.cached is True
    assert health_checker._send_health_request.call_count == 1


@pytest.mark.asyncio
async def test_health_check_opens_circuit_after_failures(
    repository: FakeServiceRepository,
    health_checker: HealthChecker,
) -> None:
    service = await repository.create(
        ServiceCreate(name="payments", url="https://payments.example.com", failure_threshold=1)
    )

    health_checker._send_health_request = AsyncMock(return_value=httpx.Response(500))

    result = await health_checker.check(service.id, use_cache=False)

    assert result.healthy is False
    assert result.circuit_state == CircuitState.OPEN


def test_service_create_rejects_private_ip_url() -> None:
    """Verify private IP health targets cannot be registered."""
    with pytest.raises(ValidationError, match="public IP address"):
        ServiceCreate(name="metadata", url="http://169.254.169.254")


def test_service_create_rejects_network_path_health_path() -> None:
    """Verify health paths cannot override the registered service host."""
    with pytest.raises(ValidationError, match="relative URL path"):
        ServiceCreate(name="orders", url="https://orders.example.com", health_check_path="//169.254.169.254/latest")


@pytest.mark.asyncio
async def test_health_check_blocks_hostname_resolving_to_private_ip(
    repository: FakeServiceRepository,
    cache: object,
    circuit_breakers: object,
    events: object,
    metrics: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify DNS resolution cannot route probes to private infrastructure."""
    service = await repository.create(ServiceCreate(name="metadata", url="http://metadata.example.com"))

    def resolve_private_address(_: str, __: int) -> set[str]:
        return {"169.254.169.254"}

    monkeypatch.setattr("app.url_security._resolve_addresses", resolve_private_address)
    async with httpx.AsyncClient() as client:
        health_checker = HealthChecker(repository, cache, circuit_breakers, events, metrics, client)
        health_checker._send_health_request = AsyncMock(return_value=httpx.Response(200))

        result = await health_checker.check(service.id, use_cache=False)

    assert result.healthy is False
    assert result.error == "service URL must resolve to a public IP address"
    health_checker._send_health_request.assert_not_called()
