import logging
from typing import Any

from celery import Celery

from app.config import get_settings
from app.logging_config import configure_logging, log_extra
from app.tracing import configure_worker_tracing

settings = get_settings()
configure_logging(settings.log_level)
configure_worker_tracing(settings)
logger = logging.getLogger(__name__)

celery_app = Celery(
    "resilience_platform",
    broker=settings.celery_broker_url or "pyamqp://guest:guest@localhost:5672//",
)


@celery_app.task(name=settings.celery_task_name)
def process_event(event: dict[str, Any]) -> None:
    """Log status events consumed from the Celery broker."""
    logger.info(
        "celery_event_processed",
        extra=log_extra(
            event_type=event.get("event_type"),
            service_id=event.get("service_id"),
        ),
    )
