import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import insert

from app.domain.models import SignalFilterResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class FilterResultRepository:
    def __init__(self, db: Session):
        self.db = db

    def bulk_insert(self, results: list[dict], signal_row_id: str) -> None:
        """
        Insert nhiều filter results cùng lúc cho 1 signal.
        Tối ưu performance dùng bulk insert.
        results là list các dict chứa: rule_code, rule_group, result, severity, score_delta, details
        """
        if not results:
            return

        # Chuẩn bị dữ liệu để insert
        insert_data = []
        now = datetime.now(timezone.utc)
        for r in results:
            insert_data.append({
                "id": str(uuid.uuid4()),
                "signal_row_id": signal_row_id,
                "rule_code": r["rule_code"],
                "rule_group": r["rule_group"],
                "result": r["result"],
                "severity": r["severity"],
                "score_delta": r.get("score_delta", 0.0),
                "details": r.get("details"),
                "created_at": now,
            })

        # Thực thi bulk insert
        self.db.execute(insert(SignalFilterResult), insert_data)
        self.db.flush()
        logger.info("filter_results_bulk_inserted", extra={"signal_row_id": signal_row_id, "count": len(results)})
