"""Unit tests for signal_bot_config validation service."""
from __future__ import annotations

import pytest

from app.services.config_validation import (
    ConfigValidationError,
    validate_signal_bot_config,
)


def test_default_signal_bot_config_validates():
    """Default config from ConfigRepository passes validation."""
    config = {
        "allowed_symbols": ["BTCUSDT", "BTCUSD"],
        "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
        "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78},
        "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10},
        "rr_min_base": 1.5,
        "market_context": {
            "enabled": False,
            "regime_mismatch_mode": "WARN",
            "snapshot_max_age_minutes": 10,
        },
    }
    result = validate_signal_bot_config(config)
    assert result is not None
    assert isinstance(result, dict)


def test_rejects_invalid_confidence_threshold_range():
    """Confidence threshold outside [0, 1] raises ConfigValidationError."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 1.5},  # Invalid: > 1
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
    }
    with pytest.raises(ConfigValidationError, match="out of range"):
        validate_signal_bot_config(config)


def test_rejects_unknown_top_level_key():
    """Unknown top-level key raises ConfigValidationError (extra='forbid')."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "unknown_key": "should_fail",
    }
    with pytest.raises(ConfigValidationError, match="Extra inputs are not permitted"):
        validate_signal_bot_config(config)


def test_accepts_market_context_warn_mode():
    """Market context with WARN mode validates successfully."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "market_context": {
            "enabled": True,
            "regime_mismatch_mode": "WARN",
            "snapshot_max_age_minutes": 15,
        },
    }
    result = validate_signal_bot_config(config)
    assert result["market_context"]["regime_mismatch_mode"] == "WARN"


def test_rejects_invalid_regime_mismatch_mode():
    """Invalid regime_mismatch_mode raises ConfigValidationError."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "market_context": {"regime_mismatch_mode": "BLOCK"},
    }
    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)
    assert "regime_mismatch_mode" in str(exc.value)


def test_rejects_snapshot_max_age_above_limit():
    """snapshot_max_age_minutes above 1440 raises ConfigValidationError."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "market_context": {"snapshot_max_age_minutes": 99999},
    }
    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)
    assert "snapshot_max_age_minutes" in str(exc.value)


def test_rejects_empty_allowed_symbols():
    """Empty string in allowed_symbols raises ConfigValidationError."""
    config = {
        "allowed_symbols": [""],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
    }
    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)
    assert "allowed_symbols" in str(exc.value)


def test_rejects_tolerance_above_one():
    """duplicate_price_tolerance_pct >= 1 raises ConfigValidationError."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "duplicate_price_tolerance_pct": 1.2,
    }
    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)
    assert "duplicate_price_tolerance_pct" in str(exc.value)


def test_accepts_rr_tolerance_zero():
    """rr_tolerance_pct=0.0 is valid per spec."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "rr_tolerance_pct": 0.0,
    }
    validated = validate_signal_bot_config(config)
    assert validated["rr_tolerance_pct"] == 0.0


def test_rejects_rr_tolerance_above_one():
    """rr_tolerance_pct >= 1 raises ConfigValidationError."""
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m"],
        "confidence_thresholds": {"1m": 0.8},
        "cooldown_minutes": {"1m": 5},
        "rr_min_base": 1.5,
        "rr_tolerance_pct": 2.0,
    }
    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)
    assert "rr_tolerance_pct" in str(exc.value)
