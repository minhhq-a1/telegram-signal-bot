import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any


SENSITIVE_KEYS = {"secret", "token", "authorization", "password", "api_key", "apikey"}
REDACTED_VALUE = "***REDACTED***"


def _sanitize_log_value(key: str | None, value: Any) -> Any:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return REDACTED_VALUE

    if isinstance(value, dict):
        return {
            nested_key: _sanitize_log_value(str(nested_key), nested_value)
            for nested_key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_sanitize_log_value(None, item) for item in value]

    if isinstance(value, tuple):
        return tuple(_sanitize_log_value(None, item) for item in value)

    return value


class JsonFormatter(logging.Formatter):
    """
    Custom formatter to output logs in JSON format.
    Ensures no sensitive data is leaked by filtering specific keys.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        
        # Add all extra fields provided via the 'extra' parameter
        # Standard record attributes to exclude
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message"
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_data[key] = _sanitize_log_value(key, value)

        return json.dumps(log_data)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    # Avoid adding multiple handlers if the logger is reused
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
    return logger

# Default logger instance
logger = get_logger("app")
