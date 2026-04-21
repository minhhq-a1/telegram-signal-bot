from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models import SignalDecision
from app.core.logging import get_logger

logger = get_logger(__name__)


class DecisionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> SignalDecision:
        """
        Lưu kết quả ra quyết định (Decision) của FilterEngine.
        data chứa: signal_row_id, decision, decision_reason, telegram_route
        """
        decision = SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=data["signal_row_id"],
            decision=data["decision"],
            decision_reason=data.get("decision_reason"),
            telegram_route=data.get("telegram_route"),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(decision)
        self.db.flush()
        logger.info("decision_created", extra={
            "signal_row_id": decision.signal_row_id, 
            "decision": decision.decision,
            "route": decision.telegram_route
        })
        return decision

    def find_by_signal_row_id(self, signal_row_id: str) -> SignalDecision | None:
        """
        Tìm decision dự theo id của signal (row_id, không phải business signal_id).
        """
        stmt = select(SignalDecision).where(SignalDecision.signal_row_id == signal_row_id)
        return self.db.execute(stmt).scalar_one_or_none()
