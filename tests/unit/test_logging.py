import json
import logging

from app.core.logging import JsonFormatter, REDACTED_VALUE


def test_json_formatter_redacts_top_level_sensitive_fields():
    formatter = JsonFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="testing",
        args=(),
        exc_info=None,
    )
    record.secret = "example-sensitive-value"
    record.token = "example-sensitive-value"
    record.signal_id = "sig-001"

    payload = json.loads(formatter.format(record))

    assert payload["secret"] == REDACTED_VALUE
    assert payload["token"] == REDACTED_VALUE
    assert payload["signal_id"] == "sig-001"


def test_json_formatter_redacts_nested_sensitive_fields():
    formatter = JsonFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=30,
        msg="nested payload",
        args=(),
        exc_info=None,
    )
    record.payload = {
        "secret": "example-sensitive-value",
        "metadata": {
            "token": "example-sensitive-value",
            "headers": {
                "Authorization": "Example Authorization Header",
            },
        },
        "items": [
            {"password": "example-sensitive-value"},
            {"safe": "value"},
        ],
    }

    payload = json.loads(formatter.format(record))

    assert payload["payload"]["secret"] == REDACTED_VALUE
    assert payload["payload"]["metadata"]["token"] == REDACTED_VALUE
    assert payload["payload"]["metadata"]["headers"]["Authorization"] == REDACTED_VALUE
    assert payload["payload"]["items"][0]["password"] == REDACTED_VALUE
    assert payload["payload"]["items"][1]["safe"] == "value"
