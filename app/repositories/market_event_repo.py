from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.domain.models import MarketEvent
from app.core.logging import get_logger

logger = get_logger(__name__)


class MarketEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_active_around(self, ts: datetime, before_min: int = 15, after_min: int = 30) -> list[MarketEvent]:
        """
        Tìm các sự kiện tin tức có tác động lớn (HIGH impact) nằm X phút trước hoặc Y phút sau thời điểm ts.
        Dùng cho quy tắc NEWS_BLOCK.
        
        Logic: Sự kiện xem như xung đột nếu: 
        (event.start_time - before_min) <= ts <= (event.end_time + after_min)
        Tương đương: ts >= (event.start_time - before_min) AND ts <= (event.end_time + after_min)
        Đảo lại theo event fields:
        event.start_time <= ts + before_min
        event.end_time >= ts - after_min
        """
        ts_plus_before = ts + timedelta(minutes=before_min)
        ts_minus_after = ts - timedelta(minutes=after_min)

        stmt = select(MarketEvent).where(
            and_(
                MarketEvent.impact == "HIGH",
                MarketEvent.start_time <= ts_plus_before,
                MarketEvent.end_time >= ts_minus_after,
            )
        )
        return list(self.db.execute(stmt).scalars().all())
