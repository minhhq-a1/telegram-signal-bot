from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.domain.models import Signal
from app.domain.schemas import SignalDetailResponse, TradingViewWebhookPayload
from app.api.dependencies import require_dashboard_auth
from app.repositories.signal_repo import SignalRepository
from app.repositories.config_repo import ConfigRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.repositories.reverify_repo import ReverifyRepository
from app.services.filter_engine import FilterEngine
from app.services.reject_codes import rule_code_to_reject_code
from app.services.signal_normalizer import SignalNormalizer

router = APIRouter(tags=["signals"])


@router.get("/api/v1/signals/{signal_id}", response_model=SignalDetailResponse)
async def get_signal_detail(signal_id: str, db: Session = Depends(get_db), _auth: None = Depends(require_dashboard_auth)):
    # Eager load các quan hệ để tránh N+1 query
    stmt = (
        select(Signal)
        .where(Signal.signal_id == signal_id)
        .options(
            joinedload(Signal.decision),
            joinedload(Signal.filter_results),
            joinedload(Signal.telegram_messages)
        )
    )

    signal = db.execute(stmt).scalars().unique().one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    return {
        "signal_id": signal.signal_id,
        "signal": signal,
        "decision": signal.decision,
        "filter_results": signal.filter_results,
        "telegram_messages": signal.telegram_messages
    }


@router.post("/api/v1/signals/{signal_id}/reverify")
def reverify_signal(
    signal_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Replay filter pipeline với rules hiện tại, không mutate bản ghi gốc.
    Persists reverify result vào signal_reverify_results.
    """
    # 1. Tìm signal gốc
    signal_repo = SignalRepository(db)
    signal = signal_repo.find_by_signal_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    # 2. Lấy original decision
    decision_repo = DecisionRepository(db)
    original = decision_repo.find_by_signal_row_id(signal.id)
    original_decision = original.decision if original else "UNKNOWN"

    # 3. Parse raw_payload và normalize lại
    raw_payload_dict = signal.raw_payload
    try:
        payload = TradingViewWebhookPayload.model_validate(raw_payload_dict)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Signal raw_payload is incompatible with current schema: {exc.errors()[0]['msg']}",
        ) from exc
    norm = SignalNormalizer.normalize(None, payload)

    # 4. Chạy filter engine với config hiện tại
    config_repo = ConfigRepository(db)
    config = config_repo.get_signal_bot_config()
    engine = FilterEngine(config, signal_repo, MarketEventRepository(db))
    result = engine.run(norm)

    # 5. Extract reject_code từ first FAIL
    first_fail = next(
        (r for r in result.filter_results if r.result.value == "FAIL"),
        None,
    )
    reject_code = rule_code_to_reject_code(first_fail.rule_code) if first_fail else None

    # 6. Extract backend score từ BACKEND_SCORE_THRESHOLD rule
    score_item = next(
        (r for r in result.filter_results if r.rule_code == "BACKEND_SCORE_THRESHOLD"),
        None,
    )
    score_value: float | None = None
    score_items: list | None = None
    if score_item and score_item.details:
        score_value = score_item.details.get("score")
        score_items = score_item.details.get("items")

    # 7. Persist reverify result (non-mutating)
    ReverifyRepository(db).create({
        "signal_row_id": signal.id,
        "original_decision": original_decision,
        "reverify_decision": result.final_decision.value,
        "reverify_score": score_value,
        "reject_code": reject_code,
        "decision_reason": result.decision_reason,
        "score_items": score_items,
        "filter_results": [r.to_dict() for r in result.filter_results],
    })
    db.commit()

    return {
        "signal_id": signal_id,
        "original_decision": original_decision,
        "reverify_decision": result.final_decision.value,
        "reverify_score": score_value,
        "reject_code": reject_code,
        "decision_reason": result.decision_reason,
    }
