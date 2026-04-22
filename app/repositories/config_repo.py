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
    _DEFAULT_SIGNAL_BOT_CONFIG: dict = {
        "allowed_symbols": ["BTCUSDT", "BTCUSD"],
        "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m"],
        "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74},
        "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
        "enable_news_block": True,
        "news_block_before_min": 15,
        "news_block_after_min": 30,
        "log_reject_to_admin": True,
    }

    def __init__(self, db: Session):
        self.db = db

    @classmethod
    def reset_cache(cls) -> None:
        """Reset class-level cache. Gọi trong test teardown để tránh cache leak."""
        cls._cached_config = None
        cls._cache_time = 0.0

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
            merged_config = {
                **ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG,
                **config_record.config_value,
            }
            # Cập nhật cache
            ConfigRepository._cached_config = merged_config
            ConfigRepository._cache_time = now
            logger.debug("signal_bot_config_reloaded_from_db")
            return merged_config
        
        logger.warning("signal_bot_config_not_found_in_db")
        return dict(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)
