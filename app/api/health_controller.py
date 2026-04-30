from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.repositories.config_repo import ConfigRepository

router = APIRouter(tags=["health"])

_REQUIRED_CONFIG_KEYS = frozenset(
    [
        "allowed_symbols",
        "allowed_timeframes",
        "confidence_thresholds",
        "cooldown_minutes",
        "rr_min_base",
        "rr_min_squeeze",
    ]
)


@router.get("/api/v1/health")
def get_health() -> dict[str, str]:
    return _live_payload()


@router.get("/api/v1/health/live")
def get_health_live() -> dict[str, str]:
    return _live_payload()


@router.get("/api/v1/health/ready")
def get_health_ready(response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    checks = {"database": "ok", "config": "ok"}

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        checks["database"] = "fail"
        return {
            "status": "degraded",
            "checks": checks,
            "detail": {"database": str(exc)},
        }

    try:
        config = ConfigRepository(db).get_signal_bot_config()
        missing_keys = sorted(_REQUIRED_CONFIG_KEYS - set(config.keys()))
        if missing_keys:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            checks["config"] = "fail"
            return {
                "status": "degraded",
                "checks": checks,
                "detail": {"config": {"missing_keys": missing_keys}},
            }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        checks["config"] = "fail"
        return {
            "status": "degraded",
            "checks": checks,
            "detail": {"config": str(exc)},
        }

    return {"status": "ok", "checks": checks}


@router.get("/api/v1/health/deps")
def get_health_deps(response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    checks = {
        "database": "ok",
        "telegram": "ok",
    }
    detail: dict[str, Any] = {}

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        checks["database"] = "fail"
        detail["database"] = str(exc)

    missing_telegram = [
        key
        for key, value in {
            "telegram_bot_token": settings.telegram_bot_token,
            "telegram_main_chat_id": settings.telegram_main_chat_id,
            "telegram_warn_chat_id": settings.telegram_warn_chat_id,
            "telegram_admin_chat_id": settings.telegram_admin_chat_id,
        }.items()
        if not value
    ]
    if missing_telegram:
        checks["telegram"] = "fail"
        detail["telegram"] = {"missing_keys": missing_telegram}

    if any(value == "fail" for value in checks.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "checks": checks, "detail": detail}

    return {"status": "ok", "checks": checks}


def _live_payload() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "telegram-signal-bot",
        "version": settings.app_version,
    }
