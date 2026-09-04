import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.config import Settings


logger = logging.getLogger(__name__)
_tracing_configured = False
_worker_tracing_configured = False


def configure_tracing(app: "FastAPI", settings: "Settings") -> None:
    """Configure OpenTelemetry tracing for the FastAPI app."""
    global _tracing_configured
    if _tracing_configured or not settings.otel_enabled:
        return

    if not _configure_trace_provider(settings):
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError as exc:
        logger.warning("opentelemetry_dependencies_missing", extra={"missing_dependency": str(exc)})
        return

    FastAPIInstrumentor.instrument_app(app, excluded_urls=r"^/health$")
    _instrument_common_clients()
    _instrument_celery()

    _tracing_configured = True
    logger.info("opentelemetry_tracing_configured")


def configure_worker_tracing(settings: "Settings") -> None:
    """Configure OpenTelemetry tracing for the Celery worker."""
    global _worker_tracing_configured
    if _worker_tracing_configured or not settings.otel_enabled:
        return

    if not _configure_trace_provider(settings):
        return

    _instrument_celery()
    _instrument_common_clients()

    _worker_tracing_configured = True
    logger.info("opentelemetry_worker_tracing_configured")


def instrument_sqlalchemy_engine(engine: "AsyncEngine") -> None:
    """Attach SQLAlchemy tracing when tracing is enabled."""
    if not (_tracing_configured or _worker_tracing_configured):
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except ImportError as exc:
        logger.warning("sqlalchemy_tracing_dependency_missing", extra={"missing_dependency": str(exc)})
        return

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


def _configure_trace_provider(settings: "Settings") -> bool:
    """Create and register the OpenTelemetry trace provider."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("opentelemetry_dependencies_missing", extra={"missing_dependency": str(exc)})
        return False

    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: settings.otel_service_name,
                "deployment.environment": settings.environment,
            }
        )
    )
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return True


def _instrument_common_clients() -> None:
    """Instrument HTTPX and Redis clients for tracing."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
    except ImportError as exc:
        logger.warning("client_tracing_dependency_missing", extra={"missing_dependency": str(exc)})
        return

    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()


def _instrument_celery() -> None:
    """Instrument Celery for trace propagation."""
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
    except ImportError as exc:
        logger.warning("celery_tracing_dependency_missing", extra={"missing_dependency": str(exc)})
        return

    CeleryInstrumentor().instrument()
