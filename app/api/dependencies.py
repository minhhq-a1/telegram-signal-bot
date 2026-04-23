from __future__ import annotations
import hmac
from fastapi import HTTPException, Request
from app.core.config import settings


def require_dashboard_auth(request: Request) -> None:
    if not settings.dashboard_token:
        return
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
    if not token or not hmac.compare_digest(token, settings.dashboard_token):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
