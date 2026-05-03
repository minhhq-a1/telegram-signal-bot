"""
Unit tests for filter rule modules (V1.3 boundary refactor).
Verifies each rule module exports expected functions and types.
"""
from app.services.filter_rules.types import FilterResult
from app.services.filter_rules import routing, validation, trade_math, business, advisory


def test_types_module_exports_filter_result():
    """Verify FilterResult is importable from types module"""
    assert FilterResult is not None


def test_routing_module_exports_check_functions():
    """Verify routing module exports expected check functions"""
    assert hasattr(routing, "check_symbol")
    assert hasattr(routing, "check_timeframe")


def test_validation_module_exports_check_functions():
    """Verify validation module exports expected check functions"""
    assert hasattr(validation, "check_confidence_range")
    assert hasattr(validation, "check_price_valid")


def test_trade_math_module_exports_check_functions():
    """Verify trade_math module exports expected check functions"""
    assert hasattr(trade_math, "check_direction_sanity")
    assert hasattr(trade_math, "check_min_rr")


def test_business_module_exports_check_functions():
    """Verify business module exports expected check functions"""
    assert hasattr(business, "check_min_confidence_by_tf")
    assert hasattr(business, "check_duplicate")
    assert hasattr(business, "check_news_block")
    assert hasattr(business, "check_regime_hard_block")


def test_advisory_module_exports_check_functions():
    """Verify advisory module exports expected check functions"""
    assert hasattr(advisory, "check_volatility")
    assert hasattr(advisory, "check_cooldown")
    assert hasattr(advisory, "check_low_volume")
    assert hasattr(advisory, "check_rr_profile_match")
    assert hasattr(advisory, "check_backend_score")
