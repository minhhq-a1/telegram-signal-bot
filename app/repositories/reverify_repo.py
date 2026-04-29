from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.domain.models import SignalReverifyResult


class ReverifyRepository:
    def __init__(self, db: Session):
        self.db = db

    REQUIRED_KEYS = frozenset(["signal_row_id", "original_decision", "reverify_decision"])

    def create(self, data: dict) -> SignalReverifyResult:
        missing = self.REQUIRED_KEYS - data.keys()
        if missing:
            raise ValueError(f"ReverifyRepository.create missing required keys: {', '.join(sorted(missing))}")
        row = SignalReverifyResult(
            id=str(uuid.uuid4()),
            signal_row_id=data["signal_row_id"],
            original_decision=data["original_decision"],
            reverify_decision=data["reverify_decision"],
            reverify_score=data.get("reverify_score"),
            reject_code=data.get("reject_code"),
            decision_reason=data.get("decision_reason"),
            score_items=data.get("score_items"),
            filter_results=data.get("filter_results"),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_for_signal(self, signal_row_id: str) -> list[SignalReverifyResult]:
        stmt = (
            select(SignalReverifyResult)
            .where(SignalReverifyResult.signal_row_id == signal_row_id)
            .order_by(SignalReverifyResult.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())
