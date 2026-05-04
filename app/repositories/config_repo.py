import copy
import time
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models import SystemConfig, SystemConfigAuditLog
from app.core.logging import get_logger
from app.services.config_validation import ConfigValidationError, validate_signal_bot_config

logger = get_logger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Dicts are merged; lists and scalars replace.

    Keys present only in base are deep-copied so the result shares no nested
    references with the original base object (important when base is a class-level
    constant like _DEFAULT_SIGNAL_BOT_CONFIG).
    """
    result: dict = {}
    all_keys = base.keys() | override.keys()
    for key in all_keys:
        in_base = key in base
        in_override = key in override
        if in_base and in_override:
            base_val, override_val = base[key], override[key]
            if isinstance(base_val, dict) and isinstance(override_val, dict):
                result[key] = _deep_merge(base_val, override_val)
            else:
                result[key] = override_val
        elif in_override:
            result[key] = override[key]
        else:
            result[key] = copy.deepcopy(base[key])
    return result


class ConfigRepository:
    # Class-level cache variables (shared across requests in same worker)
    _cached_config: dict | None = None
    _cache_time: float = 0.0
    _CACHE_TTL: int = 30  # seconds
    _DEFAULT_SIGNAL_BOT_CONFIG: dict = {
        "allowed_symbols": ["BTCUSDT", "BTCUSD"],
        "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
        "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70},
        "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
        "enable_news_block": True,
        "news_block_before_min": 15,
        "news_block_after_min": 30,
        "log_reject_to_admin": True,
        # --- V1.1 config defaults ---
        "rr_tolerance_pct": 0.10,
        "rr_target_by_type": {
            "SHORT_SQUEEZE": 2.5,
            "SHORT_V73": 1.67,
            "LONG_V73": 1.67,
        },
        "score_pass_threshold": 75,
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {
                "rsi_min": 35,
                "rsi_slope_max": -2,
                "kc_position_max": 0.55,
                "atr_pct_min": 0.20,
            },
            "SHORT_V73": {
                "rsi_min": 60,
                "stoch_k_min": 70,
            },
            "LONG_V73": {
                "rsi_max": 35,
                "stoch_k_max": 20,
            },
        },
        "rescoring": {
            "SHORT_SQUEEZE": {
                "base": 70,
                "bonuses": {
                    "vol_regime_breakout_imminent": 8,
                    "regime_weak_trend_down": 6,
                    "regime_strong_trend_down": 8,
                    "mom_direction_neg1": 5,
                    "squeeze_bars_ge_4": 3,
                    "squeeze_bars_ge_6": 5,
                    "rsi_ge_40": 4,
                    "rsi_slope_le_neg4": 4,
                    "atr_percentile_ge_70": 3,
                    "kc_position_le_040": 3,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "regime_weak_trend_up": -8,
                    "rsi_lt_35": -8,
                    "atr_pct_lt_020": -8,
                    "atr_pct_gt_150": -5,
                },
            },
            "SHORT_V73": {
                "base": 72,
                "bonuses": {
                    "rsi_ge_70": 5,
                    "stoch_ge_85": 5,
                    "rsi_slope_le_neg4": 4,
                    "regime_trend_down": 6,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "vol_ranging_high": -6,
                    "atr_pct_lt_020": -6,
                },
            },
            "LONG_V73": {
                "base": 72,
                "bonuses": {
                    "rsi_le_25": 5,
                    "stoch_le_10": 5,
                    "rsi_slope_ge_2": 4,
                    "regime_trend_up": 6,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_down": -15,
                    "vol_ranging_high": -6,
                    "atr_pct_lt_020": -6,
                },
            },
        },
        "auto_create_open_outcomes": False,
        "market_context": {
            "enabled": False,
            "regime_mismatch_mode": "WARN",
            "snapshot_max_age_minutes": 10,
        },
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
            merged_config = _deep_merge(
                ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG,
                config_record.config_value,
            )
            # Validate on read (warning only, do not raise)
            try:
                validate_signal_bot_config(merged_config)
            except ConfigValidationError as e:
                logger.warning(f"signal_bot_config_validation_failed_on_read: {e}")
            # Cập nhật cache
            ConfigRepository._cached_config = merged_config
            ConfigRepository._cache_time = now
            logger.debug("signal_bot_config_reloaded_from_db")
            return merged_config
        
        logger.warning("signal_bot_config_not_found_in_db")
        return copy.deepcopy(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)

    def get_signal_bot_config_with_version(self) -> tuple[dict, int]:
        stmt = select(SystemConfig).where(SystemConfig.config_key == "signal_bot_config")
        config_record = self.db.execute(stmt).scalar_one_or_none()
        if config_record and config_record.config_value:
            merged_config = _deep_merge(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG, config_record.config_value)
            # Validate on read (warning only, do not raise)
            try:
                validate_signal_bot_config(merged_config)
            except ConfigValidationError as e:
                logger.warning(f"signal_bot_config_validation_failed_on_read: {e}")
            return (
                merged_config,
                int(config_record.version or 1),
            )
        return copy.deepcopy(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG), 1

    def update_config_with_audit(
        self,
        config_key: str,
        new_value: dict,
        changed_by: str,
        change_reason: str,
    ) -> SystemConfig:
        # Validate on write (strict, raise on error)
        if config_key == "signal_bot_config":
            merged_for_validation = _deep_merge(
                ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG,
                new_value,
            )
            validated_value = validate_signal_bot_config(merged_for_validation)
        else:
            validated_value = new_value

        stmt = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config = self.db.execute(stmt).scalar_one_or_none()
        if config is None:
            config = SystemConfig(
                id=str(uuid.uuid4()),
                config_key=config_key,
                config_value=validated_value,
                version=1,
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(config)
            old_value = None
        else:
            old_value = copy.deepcopy(config.config_value)
            config.config_value = validated_value
            config.version = int(config.version or 1) + 1
            config.updated_at = datetime.now(timezone.utc)

        self.db.add(SystemConfigAuditLog(
            id=str(uuid.uuid4()),
            config_key=config_key,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            change_reason=change_reason,
            created_at=datetime.now(timezone.utc),
        ))
        self.db.flush()
        ConfigRepository.reset_cache()
        return config

    def list_audit_logs(self, limit: int = 50) -> list[SystemConfigAuditLog]:
        stmt = select(SystemConfigAuditLog).order_by(SystemConfigAuditLog.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
