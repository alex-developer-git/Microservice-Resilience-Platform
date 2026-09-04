import json
import logging

from app.logging_config import JsonFormatter, log_extra


def test_json_formatter_preserves_base_message_when_structured_message_is_passed() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="application_error",
        args=(),
        exc_info=None,
    )
    record._structured = log_extra(message="Service failed", service_id="svc-1")["_structured"]

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "application_error"
    assert payload["extra_message"] == "Service failed"
    assert payload["service_id"] == "svc-1"
