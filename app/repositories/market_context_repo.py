from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import MarketContextSnapshot


class MarketContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_snapshot(
        self,
        symbol: str,
        timeframe: str,
        bar_time,
        source: str | None = None,
        max_age_minutes: int = 10,
    ) -> MarketContextSnapshot | None:
        lower = bar_time - timedelta(minutes=max_age_minutes)
        stmt = (
            select(MarketContextSnapshot)
            .where(MarketContextSnapshot.symbol == symbol)
            .where(MarketContextSnapshot.timeframe == timeframe)
            .where(MarketContextSnapshot.bar_time >= lower)
            .where(MarketContextSnapshot.bar_time <= bar_time)
            .order_by(MarketContextSnapshot.bar_time.desc())
            .limit(1)
        )
        if source is not None:
            stmt = stmt.where(MarketContextSnapshot.source == source)
        return self.db.execute(stmt).scalar_one_or_none()
