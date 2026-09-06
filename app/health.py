import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

from app.cache import HealthCache
from app.circuit_breaker import CircuitBreakerManager
from app.events import EventPublisher
from app.logging_config import log_extra
from app.metrics import MetricStore
from app.models import CircuitState, HealthCheckResult, ServiceRecord, StatusEvent
from app.storage import ServiceRepository
from app.url_security import UnsafeUrlError, ensure_public_http_target

logger = logging.getLogger(__name__)


class HealthChecker:
    def __init__(
        self,
        repository: ServiceRepository,
        cache: HealthCache,
        circuit_breakers: CircuitBreakerManager,
        events: EventPublisher,
        metrics: MetricStore,
        http_client: httpx.AsyncClient,
        target_validator: Callable[[str], Awaitable[None]] = ensure_public_http_target,
    ) -> None:
        """Create a health checker with storage, cache, and events."""
        self._repository = repository
        self._cache = cache
        self._circuit_breakers = circuit_breakers
        self._events = events
        self._metrics = metrics
        self._http_client = http_client
        self._target_validator = target_validator

    async def check(self, service_id: str, *, use_cache: bool = True) -> HealthCheckResult:
        """Run or retrieve a health check for one service."""
        service = await self._repository.get(service_id)
        if use_cache:
            cached = await self._cache.get(service_id)
            if cached is not None:
                self._metrics.record_cache_hit(service_id)
                logger.info("health_check_cache_hit", extra=log_extra(service_id=service_id))
                return cached
            self._metrics.record_cache_miss(service_id)

        circuit_snapshot = self._circuit_breakers.before_request(service)
        result = await self._probe(service, circuit_snapshot.state)

        if result.healthy:
            snapshot = self._circuit_breakers.record_success(service)
        else:
            snapshot = self._circuit_breakers.record_failure(service)
        self._metrics.record_circuit_transition(service.id, circuit_snapshot.state, snapshot.state)
        result = result.model_copy(update={"circuit_state": snapshot.state})

        await self._cache.set(result, service.cache_ttl_seconds)
        self._metrics.record_health_check(result)
        await self._events.publish(
            StatusEvent(
                event_type="health_checked",
                service_id=service.id,
                payload=result.model_dump(mode="json"),
            )
        )
        logger.info(
            "health_check_completed",
            extra=log_extra(
                service_id=service.id,
                healthy=result.healthy,
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                circuit_state=result.circuit_state.value,
            ),
        )
        return result

    async def _probe(self, service: ServiceRecord, circuit_state: CircuitState) -> HealthCheckResult:
        """Send an HTTP probe and convert the response to a result."""
        if not service.enabled:
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                checked_at=datetime.now(timezone.utc),
                healthy=False,
                error="Service monitoring is disabled",
                circuit_state=circuit_state,
            )

        target_url = urljoin(str(service.url).rstrip("/") + "/", service.health_check_path.lstrip("/"))
        started_at = time.perf_counter()
        status_code: int | None = None
        error: str | None = None
        try:
            await self._target_validator(target_url)
            self._metrics.record_health_check_probe()
            response = await self._send_health_request(target_url, service.timeout_seconds)
            status_code = response.status_code
            healthy = 200 <= status_code < 300
        except (UnsafeUrlError, httpx.HTTPError) as exc:
            healthy = False
            error = str(exc)

        latency_ms = (time.perf_counter() - started_at) * 1000
        return HealthCheckResult(
            service_id=service.id,
            service_name=service.name,
            checked_at=datetime.now(timezone.utc),
            healthy=healthy,
            status_code=status_code,
            latency_ms=latency_ms,
            error=error,
            circuit_state=circuit_state,
        )

    async def _send_health_request(self, url: str, timeout_seconds: float) -> httpx.Response:
        """Send the outbound HTTP request for a health probe."""
        return await self._http_client.get(url, timeout=timeout_seconds)
