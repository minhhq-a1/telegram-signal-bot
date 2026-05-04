from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_dashboard_auth
from app.core.database import get_db
from app.repositories.config_repo import ConfigRepository, _deep_merge, diff_config_paths

router = APIRouter(prefix="/api/v1/admin/config", tags=["config"])


@router.get("/signal-bot")
def get_signal_bot_config(
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    config, version = ConfigRepository(db).get_signal_bot_config_with_version()
    return {"config_key": "signal_bot_config", "version": version, "config_value": config}


@router.get("/audit-log")
def get_config_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    rows = ConfigRepository(db).list_audit_logs(limit=limit)
    return {
        "count": len(rows),
        "logs": [
            {
                "config_key": row.config_key,
                "changed_by": row.changed_by,
                "change_reason": row.change_reason,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.put("/signal-bot")
def update_signal_bot_config(
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    change_reason = str(payload.get("change_reason") or "").strip()
    if len(change_reason) < 10:
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_REASON_REQUIRED", "message": "change_reason must be at least 10 characters"})

    config_patch = payload.get("config_value")
    if not isinstance(config_patch, dict):
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_VALIDATION_FAILED", "message": "config_value must be an object"})

    repo = ConfigRepository(db)
    current_config, _ = repo.get_signal_bot_config_with_version()
    merged = _deep_merge(current_config, config_patch)
    updated = repo.update_config_with_audit(
        config_key="signal_bot_config",
        new_value=merged,
        changed_by="dashboard-admin",
        change_reason=change_reason,
    )
    db.commit()
    return {"config_key": updated.config_key, "version": updated.version, "config_value": updated.config_value}


@router.post("/signal-bot/dry-run")
def dry_run_signal_bot_config(
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    change_reason = str(payload.get("change_reason") or "").strip()
    if len(change_reason) < 10:
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_REASON_REQUIRED", "message": "change_reason must be at least 10 characters"})
    config_patch = payload.get("config_value")
    if not isinstance(config_patch, dict):
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_VALIDATION_FAILED", "message": "config_value must be an object"})

    repo = ConfigRepository(db)
    current_config, version = repo.get_signal_bot_config_with_version()
    merged = _deep_merge(current_config, config_patch)

    from app.services.config_validation import ConfigValidationError, validate_signal_bot_config
    try:
        validated = validate_signal_bot_config(merged)
    except ConfigValidationError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_VALIDATION_FAILED", "message": str(exc)}) from exc

    return {
        "config_key": "signal_bot_config",
        "current_version": version,
        "changed_paths": diff_config_paths(current_config, validated),
        "config_value": validated,
        "warnings": [],
    }


@router.post("/signal-bot/rollback")
def rollback_signal_bot_config(
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    target_version = payload.get("target_version")
    if not isinstance(target_version, int) or target_version < 1:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_VERSION", "message": "target_version must be a positive integer"})

    change_reason = str(payload.get("change_reason") or "").strip()
    if len(change_reason) < 10:
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_REASON_REQUIRED", "message": "change_reason must be at least 10 characters"})

    repo = ConfigRepository(db)
    historic_config = repo.get_config_value_by_version("signal_bot_config", target_version)
    if historic_config is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND", "message": f"Config version {target_version} not found"})

    updated = repo.update_config_with_audit(
        config_key="signal_bot_config",
        new_value=historic_config,
        changed_by="dashboard-admin",
        change_reason=f"Rollback to version {target_version}: {change_reason}",
    )
    db.commit()

    return {
        "config_key": "signal_bot_config",
        "target_version": target_version,
        "new_version": updated.version,
        "config_value": updated.config_value,
    }
