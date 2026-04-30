from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Signal, SignalOutcome


class OutcomeRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_signal_row_id(self, signal_row_id: str) -> SignalOutcome | None:
        stmt = select(SignalOutcome).where(SignalOutcome.signal_row_id == signal_row_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def find_by_signal_id(self, signal_id: str) -> SignalOutcome | None:
        stmt = (
            select(SignalOutcome)
            .join(Signal, Signal.id == SignalOutcome.signal_row_id)
            .where(Signal.signal_id == signal_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create_open_from_signal(self, signal: Signal) -> SignalOutcome:
        existing = self.find_by_signal_row_id(signal.id)
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        outcome = SignalOutcome(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            outcome_status="OPEN",
            entry_price=float(signal.entry_price) if signal.entry_price is not None else None,
            stop_loss=float(signal.stop_loss) if signal.stop_loss is not None else None,
            take_profit=float(signal.take_profit) if signal.take_profit is not None else None,
            opened_at=signal.created_at or now,
            updated_at=now,
            created_at=now,
        )
        self.db.add(outcome)
        self.db.flush()
        return outcome

    def upsert_closed_outcome(
        self,
        signal: Signal,
        exit_price: float,
        closed_at: datetime,
        close_reason: str,
        max_favorable_price: float | None = None,
        max_adverse_price: float | None = None,
        notes: str | None = None,
    ) -> SignalOutcome:
        outcome = self.find_by_signal_row_id(signal.id)
        if outcome is None:
            outcome = self.create_open_from_signal(signal)

        outcome.outcome_status = "CLOSED"
        outcome.close_reason = close_reason
        outcome.exit_price = exit_price
        outcome.closed_at = closed_at
        outcome.updated_at = datetime.now(timezone.utc)
        outcome.max_favorable_price = max_favorable_price
        outcome.max_adverse_price = max_adverse_price
        outcome.notes = notes
        self.db.flush()
        return outcome

    def list_recent(self, days: int, limit: int) -> list[SignalOutcome]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(SignalOutcome)
            .where(SignalOutcome.created_at >= since)
            .order_by(SignalOutcome.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())
