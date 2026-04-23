from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.domain.models import Signal
from app.domain.schemas import SignalDetailResponse
from app.api.dependencies import require_dashboard_auth

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
        
    # Chuyển đổi ORM sang Schema (Pydantic will handle this thanks to model_config from_attributes=True)
    # Tuy nhiên vì cấu trúc SignalDetailResponse mới của bạn hơi khác, tôi sẽ map thủ công
    
    return {
        "signal_id": signal.signal_id,
        "signal": signal, # Pydantic sẽ map các fields của Signal vào SignalDataResponse
        "decision": signal.decision,
        "filter_results": signal.filter_results,
        "telegram_messages": signal.telegram_messages
    }
