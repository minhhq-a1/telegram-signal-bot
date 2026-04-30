import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models import WebhookEvent
from app.core.logging import get_logger

logger = get_logger(__name__)


class WebhookEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> WebhookEvent:
        """
        Insert 1 webhook event record vào DB.
        """
        event = WebhookEvent(
            id=str(uuid.uuid4()),
            correlation_id=data.get("correlation_id"),
            raw_body=data.get("raw_body", {}),
            is_valid_json=data.get("is_valid_json", True),
            http_headers=data.get("http_headers"),
            auth_status=data.get("auth_status"),
            error_message=data.get("error_message"),
            source_ip=data.get("source_ip"),
            received_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.flush()  # flush để lấy id, chưa commit
        logger.info(
            "webhook_event_created",
            extra={"event_id": event.id, "correlation_id": event.correlation_id},
        )
        return event

    def mark_auth_failure(self, id: str, reason: str) -> None:
        """
        Cập nhật auth_status và error_message cho event đã tồn tại.
        Dùng khi auth thất bại sau khi record đã được flush.
        """
        stmt = select(WebhookEvent).where(WebhookEvent.id == id)
        event = self.db.execute(stmt).scalar_one_or_none()
        if event:
            event.auth_status = "INVALID_SECRET"
            event.error_message = reason
            self.db.flush()
            logger.warning(
                "webhook_auth_failure",
                extra={"event_id": id, "reason": reason, "correlation_id": event.correlation_id},
            )
