import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models import TelegramMessage
from app.core.logging import get_logger

logger = get_logger(__name__)


class TelegramRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> TelegramMessage:
        """
        Record việc gửi message lên Telegram vào log.
        data chứa: signal_row_id, chat_id, route, message_text, delivery_status
        """
        message = TelegramMessage(
            id=str(uuid.uuid4()),
            signal_row_id=data.get("signal_row_id"),
            chat_id=data["chat_id"],
            route=data["route"],
            message_text=data["message_text"],
            delivery_status=data.get("delivery_status", "PENDING"),
            telegram_message_id=data.get("telegram_message_id"),
            error_log=data.get("error_log"),
            sent_at=data.get("sent_at"),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(message)
        self.db.flush()
        logger.info("telegram_message_log_created", extra={"telegram_message_row_id": message.id})
        return message

    def mark_sent(self, id: str, telegram_message_id: str, sent_at: datetime) -> None:
        """
        Mark là SENT khi nhận được API response payload từ Telegram thành công.
        """
        stmt = select(TelegramMessage).where(TelegramMessage.id == id)
        msg = self.db.execute(stmt).scalar_one_or_none()
        if msg:
            msg.delivery_status = "SENT"
            msg.telegram_message_id = telegram_message_id
            msg.sent_at = sent_at
            self.db.flush()
            logger.info("telegram_message_marked_sent", extra={"telegram_message_row_id": id})

    def mark_failed(self, id: str, error: str) -> None:
        """
        Mark là FAILED nếu sau khi retry hết không gửi được.
        """
        stmt = select(TelegramMessage).where(TelegramMessage.id == id)
        msg = self.db.execute(stmt).scalar_one_or_none()
        if msg:
            msg.delivery_status = "FAILED"
            msg.error_log = error
            self.db.flush()
            logger.warning("telegram_message_marked_failed", extra={"telegram_message_row_id": id, "error": error})
