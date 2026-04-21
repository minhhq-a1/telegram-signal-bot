from typing import Optional
import time
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models import SystemConfig
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConfigRepository:
    # Class-level cache variables (shared across requests in same worker)
    _cached_config: Optional[dict] = None
    _cache_time: float = 0.0
    _CACHE_TTL: int = 30  # seconds

    def __init__(self, db: Session):
        self.db = db

    def get_signal_bot_config(self) -> dict:
        """
        Lấy cấu hình cho signal bot từ table system_configs.
        Có simple TTL cache 30s để tránh hit DB trên mọi payload đến.
        """
        now = time.time()
        # Trả về cache nếu còn hợp lệ
        if self._cached_config is not None and (now - self._cache_time) < self._CACHE_TTL:
            return self._cached_config

        # Cache miss / expired -> Đọc từ DB
        stmt = select(SystemConfig).where(SystemConfig.config_key == "signal_bot_config")
        config_record = self.db.execute(stmt).scalar_one_or_none()

        if config_record and config_record.config_value:
            # Cập nhật cache
            ConfigRepository._cached_config = config_record.config_value
            ConfigRepository._cache_time = now
            logger.debug("signal_bot_config_reloaded_from_db")
            return config_record.config_value
        
        logger.warning("signal_bot_config_not_found_in_db")
        return {}
