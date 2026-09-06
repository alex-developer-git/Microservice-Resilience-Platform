import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app.cache import HealthCache, RedisHealthCache
from app.circuit_breaker import CircuitBreakerManager
from app.config import Settings, get_settings
from app.errors import AppError
from app.events import CeleryEventPublisher, EventPublisher, RealtimeEventPublisher
from app.health import HealthChecker
from app.logging_config import configure_logging, log_extra, reset_correlation_id, set_correlation_id
from app.metrics import MetricStore
from app.models import CircuitBreakerSnapshot, HealthCheckResult, ServiceCreate, ServiceResponse, StatusEvent
from app.storage import PostgresServiceRepository, ServiceRepository
from app.tracing import configure_tracing
from app.websocket import WebSocketStatusManager

logger = logging.getLogger(__name__)
CORRELATION_ID_HEADER = "X-Correlation-ID"


class AppState:
    def __init__(
        self,
        repository: ServiceRepository,
        cache: HealthCache,
        events: EventPublisher,
        circuit_breakers: CircuitBreakerManager,
        metrics: MetricStore,
        websocket_manager: WebSocketStatusManager,
        http_client: httpx.AsyncClient,
    ) -> None:
        """Store initialized application dependencies."""
        self.repository = repository
        self.cache = cache
        self.events = events
        self.circuit_breakers = circuit_breakers
        self.metrics = metrics
        self.websocket_manager = websocket_manager
        self.http_client = http_client
        self.health_checker = HealthChecker(repository, cache, circuit_breakers, events, metrics, http_client)


def build_state(settings: Settings) -> AppState:
    """Create runtime dependencies from validated settings."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required. Run Alembic migrations before starting the application.")
    repository: ServiceRepository = PostgresServiceRepository(settings.database_url)

    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is required for health check result caching.")
    cache: HealthCache = RedisHealthCache(settings.redis_url)

    websocket_manager = WebSocketStatusManager()
    if not settings.celery_broker_url:
        raise RuntimeError("CELERY_BROKER_URL is required for asynchronous event processing.")
    celery_events = CeleryEventPublisher(settings.celery_broker_url, settings.celery_task_name)
    events: EventPublisher = RealtimeEventPublisher(celery_events, websocket_manager)
    http_client = httpx.AsyncClient(headers={"User-Agent": "resilience-platform/1.0"}, follow_redirects=False)

    return AppState(
        repository=repository,
        cache=cache,
        events=events,
        circuit_breakers=CircuitBreakerManager(),
        metrics=MetricStore(),
        websocket_manager=websocket_manager,
        http_client=http_client,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and clean up application resources."""
    settings = get_settings()
    configure_logging(settings.log_level)
    state = build_state(settings)
    app.state.container = state
    await state.repository.init()
    await _record_service_inventory(state)
    logger.info("application_started", extra=log_extra(environment=settings.environment))
    try:
        yield
    finally:
        await state.events.close()
        await state.http_client.aclose()
        await state.cache.close()
        await state.repository.close()
        logger.info("application_stopped")


app = FastAPI(title="Microservice Resilience Platform", lifespan=lifespan)
configure_tracing(app, get_settings())


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Attach a correlation ID to request logs and responses."""
    correlation_id = _request_correlation_id(request)
    token = set_correlation_id(correlation_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        _record_http_metrics(request, status.HTTP_500_INTERNAL_SERVER_ERROR, duration_ms / 1000)
        logger.exception(
            "request_failed",
            extra=log_extra(method=request.method, path=request.url.path, duration_ms=round(duration_ms, 2)),
        )
        reset_correlation_id(token)
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    _record_http_metrics(request, response.status_code, duration_ms / 1000)
    response.headers[CORRELATION_ID_HEADER] = correlation_id
    logger.info(
        "request_completed",
        extra=log_extra(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        ),
    )
    reset_correlation_id(token)
    return response


def _request_correlation_id(request: Request) -> str:
    """Return a safe caller-provided correlation ID or generate a new one."""
    correlation_id = request.headers.get(CORRELATION_ID_HEADER)
    if correlation_id and 1 <= len(correlation_id) <= 128:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/")
        if all(character in allowed for character in correlation_id):
            return correlation_id
    return str(uuid4())


def _record_http_metrics(request: Request, status_code: int, duration_seconds: float) -> None:
    """Record HTTP metrics when the application state has been initialized."""
    try:
        metrics = request.app.state.container.metrics
    except AttributeError:
        return
    metrics.record_http_request(request.method, _route_path(request), status_code, duration_seconds)


def _route_path(request: Request) -> str:
    """Return the FastAPI route template for stable Prometheus labels."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return request.url.path


async def _record_service_inventory(state: AppState) -> None:
    """Refresh service inventory business metrics."""
    if not hasattr(state.metrics, "record_service_inventory"):
        return
    try:
        services = await state.repository.list()
    except Exception as exc:
        logger.warning("service_inventory_metric_failed", extra=log_extra(error=str(exc)))
        return
    state.metrics.record_service_inventory(
        total=len(services),
        enabled=sum(1 for service in services if service.enabled),
    )


def get_app_state(request: Request) -> AppState:
    """Return the dependency container attached to the FastAPI app."""
    return request.app.state.container


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Convert known application errors to structured responses."""
    logger.warning("application_error", extra=log_extra(code=exc.code, message=exc.message))
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Convert unexpected errors to generic structured responses."""
    logger.exception("unhandled_error", extra=log_extra(error=str(exc)))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "Unexpected server error"}},
    )


@app.get("/health")
async def container_health() -> dict[str, str]:
    """Return a lightweight container health response."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    """Check readiness of database, cache, and event broker."""
    state = get_app_state(request)
    checks = {
        "postgres": await _check_dependency(state.repository.init),
        "redis": await _check_dependency(state.cache.ping),
        "celery_broker": await _check_dependency(state.events.ping),
    }
    ready = all(check["status"] == "ok" for check in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


async def _check_dependency(check: Callable[[], Awaitable[None]]) -> dict[str, str]:
    """Run a dependency check and return a readiness status."""
    try:
        await check()
    except Exception as exc:
        logger.warning("readiness_check_failed", extra=log_extra(error=str(exc)))
        return {"status": "unavailable", "error": str(exc)}
    return {"status": "ok"}


@app.post("/register-service", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def register_service(request: Request, payload: ServiceCreate) -> ServiceResponse:
    """Register a new external service for monitoring."""
    state = get_app_state(request)
    record = await state.repository.create(payload)
    state.metrics.record_service_registered()
    await _record_service_inventory(state)
    event = StatusEvent(
        event_type="service_registered",
        service_id=record.id,
        payload=ServiceResponse.model_validate(record).model_dump(mode="json"),
    )
    await state.events.publish(event)
    logger.info("service_registered", extra=log_extra(service_id=record.id, service_name=record.name))
    return ServiceResponse.model_validate(record)


@app.get("/health/{service_id}", response_model=HealthCheckResult)
async def get_health(service_id: str, request: Request) -> HealthCheckResult:
    """Run a health check for a registered service."""
    state = get_app_state(request)
    return await state.health_checker.check(service_id)


@app.post("/circuit-breaker/{service_id}/trip", response_model=CircuitBreakerSnapshot)
async def trip_circuit_breaker(service_id: str, request: Request) -> CircuitBreakerSnapshot:
    """Manually open a service circuit breaker."""
    state = get_app_state(request)
    await state.repository.get(service_id)
    previous_state = state.circuit_breakers.snapshot(service_id).state
    snapshot = state.circuit_breakers.trip(service_id)
    state.metrics.record_manual_trip(service_id, previous_state)
    await state.events.publish(
        StatusEvent(
            event_type="circuit_breaker_tripped",
            service_id=service_id,
            payload=snapshot.model_dump(mode="json"),
        )
    )
    logger.warning("circuit_breaker_tripped", extra=log_extra(service_id=service_id))
    return snapshot


@app.post("/alerts/alertmanager", status_code=status.HTTP_202_ACCEPTED)
async def receive_alertmanager_webhook(request: Request, payload: dict[str, Any]) -> dict[str, int]:
    """Receive Alertmanager webhooks and forward them to realtime status clients."""
    state = get_app_state(request)
    raw_alerts = payload.get("alerts")
    alerts = raw_alerts if isinstance(raw_alerts, list) else []
    forwarded = 0

    for raw_alert in alerts:
        if not isinstance(raw_alert, dict):
            continue
        labels = _alert_dict(raw_alert.get("labels"))
        annotations = _alert_dict(raw_alert.get("annotations"))
        service_id = _alert_service_id(labels)
        event = StatusEvent(
            event_type="alertmanager_alert",
            service_id=service_id,
            payload={
                "status": raw_alert.get("status"),
                "receiver": payload.get("receiver"),
                "group_key": payload.get("groupKey"),
                "labels": labels,
                "annotations": annotations,
                "starts_at": raw_alert.get("startsAt"),
                "ends_at": raw_alert.get("endsAt"),
                "generator_url": raw_alert.get("generatorURL"),
                "fingerprint": raw_alert.get("fingerprint"),
            },
        )
        await state.websocket_manager.broadcast(event.model_dump(mode="json"))
        forwarded += 1
        logger.warning(
            "alertmanager_alert_received",
            extra=log_extra(
                alertname=labels.get("alertname"),
                service_id=service_id,
                severity=labels.get("severity"),
                alert_status=raw_alert.get("status"),
            ),
        )

    return {"received": len(alerts), "forwarded": forwarded}


def _alert_dict(value: object) -> dict[str, str]:
    """Return Alertmanager label or annotation maps as string dictionaries."""
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _alert_service_id(labels: dict[str, str]) -> str:
    """Extract a stable service identifier from Alertmanager labels."""
    return labels.get("service_id") or labels.get("instance") or "unknown"


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics for scraping."""
    state = get_app_state(request)
    return Response(content=state.metrics.render_prometheus(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket) -> None:
    """Stream initial and future service status events over WebSocket."""
    state: AppState = websocket.app.state.container
    await state.websocket_manager.connect(websocket)
    try:
        services = await state.repository.list()
        await websocket.send_json(
            {
                "event_type": "snapshot",
                "services": [
                    {
                        "service": ServiceResponse.model_validate(service).model_dump(mode="json"),
                        "circuit_breaker": state.circuit_breakers.snapshot(service.id).model_dump(mode="json"),
                    }
                    for service in services
                ],
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.websocket_manager.disconnect(websocket)
