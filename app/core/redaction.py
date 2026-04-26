from __future__ import annotations

import re
from typing import Any

REDACTED_VALUE = "***REDACTED***"
_SENSITIVE_MARKERS = ("secret", "token", "authorization", "password", "apikey")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _is_sensitive_key(key: str | None) -> bool:
    if key is None:
        return False
    normalized = _NON_ALNUM_RE.sub("", key.lower())
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)


def redact_sensitive_payload(value: Any, key: str | None = None) -> Any:
    if _is_sensitive_key(key):
        return REDACTED_VALUE

    if isinstance(value, dict):
        return {
            nested_key: redact_sensitive_payload(nested_value, str(nested_key))
            for nested_key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_payload(item) for item in value)

    return value
