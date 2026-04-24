"""Unit tests for T4: _deep_merge and ConfigRepository deep merge semantics."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.repositories.config_repo import ConfigRepository, _deep_merge


# ── _deep_merge unit tests ────────────────────────────────────────────────────

def test_deep_merge_scalar_override():
    base = {"rr_min_base": 1.5, "enable_news_block": True}
    override = {"rr_min_base": 2.0}
    result = _deep_merge(base, override)
    assert result["rr_min_base"] == 2.0
    assert result["enable_news_block"] is True


def test_deep_merge_nested_partial_override():
    base = {"confidence_thresholds": {"1m": 0.82, "5m": 0.78, "1h": 0.70}}
    override = {"confidence_thresholds": {"5m": 0.95}}
    result = _deep_merge(base, override)
    assert result["confidence_thresholds"]["5m"] == 0.95
    assert result["confidence_thresholds"]["1m"] == 0.82
    assert result["confidence_thresholds"]["1h"] == 0.70


def test_deep_merge_list_replaced_not_merged():
    base = {"allowed_symbols": ["BTCUSDT", "BTCUSD"]}
    override = {"allowed_symbols": ["ETHUSDT"]}
    result = _deep_merge(base, override)
    assert result["allowed_symbols"] == ["ETHUSDT"]


def test_deep_merge_new_key_added():
    base = {"rr_min_base": 1.5}
    override = {"new_key": "new_value"}
    result = _deep_merge(base, override)
    assert result["new_key"] == "new_value"
    assert result["rr_min_base"] == 1.5


def test_deep_merge_does_not_mutate_base():
    base = {"confidence_thresholds": {"1m": 0.82}}
    override = {"confidence_thresholds": {"1m": 0.90}}
    _deep_merge(base, override)
    assert base["confidence_thresholds"]["1m"] == 0.82


def test_deep_merge_does_not_mutate_override():
    base = {"confidence_thresholds": {"1m": 0.82}}
    override = {"confidence_thresholds": {"1m": 0.90}}
    _deep_merge(base, override)
    assert override["confidence_thresholds"]["1m"] == 0.90


def test_deep_merge_empty_override_returns_copy():
    base = {"rr_min_base": 1.5, "enable_news_block": True}
    result = _deep_merge(base, {})
    assert result == base
    assert result is not base


def test_deep_merge_empty_base_returns_override():
    override = {"rr_min_base": 2.0}
    result = _deep_merge({}, override)
    assert result == override


def test_deep_merge_cooldown_partial_override():
    base = {"cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "1h": 90}}
    override = {"cooldown_minutes": {"1h": 120}}
    result = _deep_merge(base, override)
    assert result["cooldown_minutes"]["1h"] == 120
    assert result["cooldown_minutes"]["1m"] == 5
    assert result["cooldown_minutes"]["5m"] == 10


def test_deep_merge_type_mismatch_override_wins():
    base = {"confidence_thresholds": {"1m": 0.82}}
    override = {"confidence_thresholds": "disabled"}
    result = _deep_merge(base, override)
    assert result["confidence_thresholds"] == "disabled"


# ── Regression guard ──────────────────────────────────────────────────────────

def test_shallow_merge_regression():
    """Documents the bug that deep merge fixes."""
    defaults = {"confidence_thresholds": {"1m": 0.82, "5m": 0.78}}
    db_config = {"confidence_thresholds": {"5m": 0.95}}

    shallow = {**defaults, **db_config}
    assert "1m" not in shallow["confidence_thresholds"]  # shallow LOSES 1m

    deep = _deep_merge(defaults, db_config)
    assert deep["confidence_thresholds"]["1m"] == 0.82  # deep preserves it
    assert deep["confidence_thresholds"]["5m"] == 0.95


# ── ConfigRepository integration ─────────────────────────────────────────────

def test_get_signal_bot_config_deep_merges_nested_dicts():
    """Partial confidence_thresholds in DB does not wipe other timeframes."""
    from sqlalchemy import select
    from app.domain.models import SystemConfig

    db_mock = MagicMock()
    mock_record = MagicMock()
    mock_record.config_value = {
        "confidence_thresholds": {"5m": 0.95},
        "rr_min_base": 2.5,
    }
    db_mock.execute.return_value.scalar_one_or_none.return_value = mock_record

    ConfigRepository.reset_cache()
    repo = ConfigRepository(db=db_mock)
    config = repo.get_signal_bot_config()

    assert config["confidence_thresholds"]["5m"] == 0.95
    assert config["confidence_thresholds"]["1m"] == 0.82
    assert config["confidence_thresholds"]["1h"] == 0.70
    assert config["rr_min_base"] == 2.5
    ConfigRepository.reset_cache()


# ── Immutability tests ────────────────────────────────────────────────────────

def test_merged_config_does_not_share_nested_reference_with_defaults():
    """Mutating the returned config must not affect _DEFAULT_SIGNAL_BOT_CONFIG."""
    original_1m = ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG["confidence_thresholds"]["1m"]

    db_mock = MagicMock()
    mock_record = MagicMock()
    mock_record.config_value = {"confidence_thresholds": {"5m": 0.95}}
    db_mock.execute.return_value.scalar_one_or_none.return_value = mock_record

    ConfigRepository.reset_cache()
    repo = ConfigRepository(db=db_mock)
    config = repo.get_signal_bot_config()

    config["confidence_thresholds"]["1m"] = 0.0
    assert ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG["confidence_thresholds"]["1m"] == original_1m
    ConfigRepository.reset_cache()


def test_fallback_config_does_not_share_nested_reference_with_defaults():
    """Mutating the fallback config (no DB row) must not affect _DEFAULT_SIGNAL_BOT_CONFIG."""
    original_symbols = ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG["allowed_symbols"]

    db_mock = MagicMock()
    db_mock.execute.return_value.scalar_one_or_none.return_value = None

    ConfigRepository.reset_cache()
    repo = ConfigRepository(db=db_mock)
    config = repo.get_signal_bot_config()

    config["allowed_symbols"].append("POISONED")
    assert ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG["allowed_symbols"] is original_symbols
    assert "POISONED" not in ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG["allowed_symbols"]
    ConfigRepository.reset_cache()
