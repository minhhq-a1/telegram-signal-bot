"""Unit tests for signal_bot_config validation service."""
from __future__ import annotations

import pytest

from app.services.config_validation import (
    ConfigValidationError,
    validate_signal_bot_config,
)


def test_valid_minimal_config():
    """Minimal valid config passes."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "market_context": {},
    }
    validate_signal_bot_config(config)  # Should not raise


def test_missing_required_key_raises():
    """Missing required top-level key raises ConfigValidationError."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        # missing allowed_timeframes
    }
    with pytest.raises(ConfigValidationError, match="allowed_timeframes"):
        validate_signal_bot_config(config)


def test_invalid_type_raises():
    """Invalid type for a field raises ConfigValidationError."""
    config = {
        "allowed_symbols": "BTCUSDT",  # should be list
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "market_context": {},
    }
    with pytest.raises(ConfigValidationError):
        validate_signal_bot_config(config)


def test_extra_keys_allowed():
    """Extra keys are allowed (forward compatibility)."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "market_context": {},
        "future_feature_flag": True,
    }
    validate_signal_bot_config(config)  # Should not raise
