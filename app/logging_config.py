import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    _reserved_keys = {"timestamp", "level", "logger", "message", "exception"}

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as structured JSON."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        trace_context = _trace_context()
        if trace_context:
            payload.update(trace_context)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        structured = getattr(record, "_structured", None)
        if isinstance(structured, dict):
            for key, value in structured.items():
                output_key = f"extra_{key}" if key in self._reserved_keys else key
                payload[output_key] = value

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Configure root logging to emit JSON to stdout."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """Wrap structured log fields for the JSON formatter."""
    return {"_structured": kwargs}


def set_correlation_id(correlation_id: str) -> Token[str | None]:
    """Store the request correlation ID for logs emitted in the current context."""
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token[str | None]) -> None:
    """Restore the previous correlation ID context."""
    _correlation_id.reset(token)


def get_correlation_id() -> str | None:
    """Return the correlation ID for the current context."""
    return _correlation_id.get()


def _trace_context() -> dict[str, str]:
    """Return OpenTelemetry trace identifiers when a span is active."""
    try:
        from opentelemetry import trace
    except ImportError:
        return {}

    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }
