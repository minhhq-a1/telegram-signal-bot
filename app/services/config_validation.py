"""Validation service for signal_bot_config using Pydantic v2."""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError


class ConfigValidationError(Exception):
    """Raised when signal_bot_config validation fails."""
    pass


class SignalBotConfigSchema(BaseModel):
    """Pydantic v2 schema for signal_bot_config.

    Extra keys are allowed for forward compatibility (e.g., future feature flags).
    """
    model_config = {"extra": "allow"}

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
    market_context: dict = Field(default_factory=dict)


def validate_signal_bot_config(config: dict) -> None:
    """Validate signal_bot_config against schema.

    Args:
        config: The config dict to validate

    Raises:
        ConfigValidationError: If validation fails
    """
    try:
        SignalBotConfigSchema.model_validate(config)
    except ValidationError as e:
        raise ConfigValidationError(f"Invalid signal_bot_config: {e}") from e
