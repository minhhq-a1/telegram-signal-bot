from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import MarketContextSnapshot


class MarketContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_snapshot(self, symbol: str, timeframe: str, bar_time) -> MarketContextSnapshot | None:
        stmt = (
            select(MarketContextSnapshot)
            .where(MarketContextSnapshot.symbol == symbol)
            .where(MarketContextSnapshot.timeframe == timeframe)
            .where(MarketContextSnapshot.bar_time == bar_time)
        )
        return self.db.execute(stmt).scalar_one_or_none()
