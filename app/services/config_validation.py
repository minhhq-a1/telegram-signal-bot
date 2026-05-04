"""Validation service for signal_bot_config using Pydantic v2."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


class ConfigValidationError(Exception):
    """Raised when signal_bot_config validation fails."""
    pass


class MarketContextConfig(BaseModel):
    """Nested model for market_context configuration."""
    model_config = {"extra": "forbid"}

    enabled: bool = False
    regime_mismatch_mode: Literal["WARN"] = "WARN"
    snapshot_max_age_minutes: int = Field(default=10, ge=1, le=1440)


class SignalBotConfigModel(BaseModel):
    """Pydantic v2 schema for signal_bot_config.

    Extra keys are forbidden to catch typos and invalid config keys.
    """
    model_config = {"extra": "forbid"}

    allowed_symbols: list[str] = Field(min_length=1)
    allowed_timeframes: list[str] = Field(min_length=1)
    confidence_thresholds: dict[str, float]
    cooldown_minutes: dict[str, int]
    rr_min_base: float = Field(gt=0)
    rr_min_squeeze: float | None = Field(default=None, gt=0)
    duplicate_price_tolerance_pct: float | None = Field(default=None, ge=0)
    enable_news_block: bool | None = None
    news_block_before_min: int | None = Field(default=None, ge=0)
    news_block_after_min: int | None = Field(default=None, ge=0)
    log_reject_to_admin: bool | None = None
    rr_tolerance_pct: float | None = Field(default=None, ge=0)
    rr_target_by_type: dict[str, float] | None = None
    score_pass_threshold: int | None = Field(default=None, ge=0, le=100)
    strategy_thresholds: dict[str, dict] | None = None
    rescoring: dict[str, dict] | None = None
    auto_create_open_outcomes: bool | None = None
    market_context: MarketContextConfig = Field(default_factory=MarketContextConfig)

    @field_validator("confidence_thresholds")
    @classmethod
    def validate_confidence_range(cls, v: dict[str, float]) -> dict[str, float]:
        """Ensure all confidence threshold values are in [0, 1]."""
        for timeframe, threshold in v.items():
            if not (0 <= threshold <= 1):
                raise ValueError(
                    f"confidence_thresholds[{timeframe}] = {threshold} out of range [0, 1]"
                )
        return v

    @field_validator("cooldown_minutes")
    @classmethod
    def validate_cooldown_positive(cls, v: dict[str, int]) -> dict[str, int]:
        """Ensure all cooldown values are positive."""
        for timeframe, minutes in v.items():
            if minutes <= 0:
                raise ValueError(
                    f"cooldown_minutes[{timeframe}] = {minutes} must be positive"
                )
        return v

    @field_validator("allowed_symbols", "allowed_timeframes")
    @classmethod
    def non_empty_string_list(cls, value: list[str]) -> list[str]:
        """Ensure list contains at least one non-empty string."""
        if not value or any(not item.strip() for item in value):
            raise ValueError("must contain at least one non-empty string")
        return value

    @field_validator("duplicate_price_tolerance_pct", "rr_tolerance_pct")
    @classmethod
    def percentage_below_one(cls, value: float | None) -> float | None:
        """Ensure percentage values are between 0 and 1 (exclusive)."""
        if value is not None and not (0.0 < value < 1.0):
            raise ValueError("must be between 0 and 1 (exclusive)")
        return value


def validate_signal_bot_config(config: dict) -> dict:
    """Validate signal_bot_config against schema.

    Args:
        config: The config dict to validate

    Returns:
        The validated config as a dict (Pydantic model dumped back to dict)

    Raises:
        ConfigValidationError: If validation fails
    """
    try:
        validated_model = SignalBotConfigModel.model_validate(config)
        return validated_model.model_dump()
    except ValidationError as e:
        raise ConfigValidationError(f"Invalid signal_bot_config: {e}") from e
