"""Rate limiter initialization for FastAPI endpoints."""
from __future__ import annotations

import re

from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

_RATE_LIMIT_DETAIL_RE = re.compile(
    r"(?P<count>\d+)\s+per\s+(?P<window>\d+)\s+(?P<unit>second|minute|hour|day)",
    re.IGNORECASE,
)
_UNIT_TO_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}

limiter = Limiter(key_func=get_remote_address)


def _retry_after_from_detail(detail: str) -> int | None:
    """Parse slowapi detail like '3 per 1 minute' into Retry-After seconds."""
    match = _RATE_LIMIT_DETAIL_RE.search(detail)
    if not match:
        return None

    window = int(match.group("window"))
    unit = match.group("unit").lower()
    return window * _UNIT_TO_SECONDS[unit]


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return slowapi's 429 response and guarantee a Retry-After header."""
    response = _rate_limit_exceeded_handler(request, exc)
    if "Retry-After" not in response.headers and "retry-after" not in response.headers:
        retry_after = _retry_after_from_detail(str(exc.detail))
        if retry_after is not None:
            response.headers["Retry-After"] = str(retry_after)
    return response
