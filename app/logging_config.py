import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


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
