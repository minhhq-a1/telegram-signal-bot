from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_dashboard_auth
from app.core.database import get_db
from app.domain.schemas import OutcomeListResponse, OutcomeOpenRequest, OutcomeUpsertRequest, SignalOutcomeSchema
from app.repositories.outcome_repo import OutcomeRepository
from app.repositories.signal_repo import SignalRepository

router = APIRouter(tags=["outcomes"])


@router.post("/api/v1/signals/{signal_id}/outcome/open", response_model=SignalOutcomeSchema)
def open_signal_outcome(
    signal_id: str,
    payload: OutcomeOpenRequest | None = None,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    signal = SignalRepository(db).find_by_signal_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail={"error_code": "SIGNAL_NOT_FOUND", "message": "Signal not found"})

    repo = OutcomeRepository(db)
    outcome = repo.create_open_from_signal(signal)
    if payload and payload.notes:
        outcome.notes = payload.notes
    db.commit()
    db.refresh(outcome)
    return outcome


@router.put("/api/v1/signals/{signal_id}/outcome", response_model=SignalOutcomeSchema)
def close_signal_outcome(
    signal_id: str,
    payload: OutcomeUpsertRequest,
    allow_reject_outcome: bool = Query(default=False),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    signal = SignalRepository(db).find_by_signal_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail={"error_code": "SIGNAL_NOT_FOUND", "message": "Signal not found"})

    if not allow_reject_outcome and getattr(signal.decision, "decision", None) == "REJECT":
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_OUTCOME_VALUES", "message": "Reject outcomes require allow_reject_outcome=true"})

    repo = OutcomeRepository(db)
    outcome = repo.upsert_closed_outcome(
        signal=signal,
        exit_price=payload.exit_price,
        closed_at=payload.closed_at,
        close_reason=payload.close_reason,
        max_favorable_price=payload.max_favorable_price,
        max_adverse_price=payload.max_adverse_price,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(outcome)
    return outcome


@router.get("/api/v1/signals/{signal_id}/outcome", response_model=SignalOutcomeSchema)
def get_signal_outcome(
    signal_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    outcome = OutcomeRepository(db).find_by_signal_id(signal_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail={"error_code": "OUTCOME_NOT_FOUND", "message": "Outcome not found"})
    return outcome


@router.get("/api/v1/outcomes/recent", response_model=OutcomeListResponse)
def list_recent_outcomes(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    outcomes = OutcomeRepository(db).list_recent(days=days, limit=limit)
    return {"count": len(outcomes), "outcomes": outcomes}
