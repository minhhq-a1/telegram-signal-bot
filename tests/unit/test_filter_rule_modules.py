"""
Unit tests for filter rule modules (V1.3 boundary refactor).
Tests actual behavior of extracted routing and validation helpers.
"""
from __future__ import annotations

from app.core.enums import DecisionType, RuleResult, RuleSeverity, TelegramRoute
from app.services.filter_rules.routing import decide, build_decision_reason
from app.services.filter_rules.types import FilterResult
from app.services.filter_rules.validation import check_symbol, check_timeframe


def test_decide_rejects_on_any_fail() -> None:
    results = [FilterResult("SYMBOL_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL)]

    decision, route = decide(results)

    assert decision == DecisionType.REJECT
    assert route == TelegramRoute.NONE


def test_decide_warns_on_medium_warn() -> None:
    results = [FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM)]

    decision, route = decide(results)

    assert decision == DecisionType.PASS_WARNING
    assert route == TelegramRoute.WARN


def test_decide_passes_main_on_low_warn_only() -> None:
    results = [FilterResult("VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW)]

    decision, route = decide(results)

    assert decision == DecisionType.PASS_MAIN
    assert route == TelegramRoute.MAIN


def test_build_decision_reason_lists_medium_warns_only_for_warning_route() -> None:
    results = [
        FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM),
        FilterResult("VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW),
    ]

    reason = build_decision_reason("Filters passed", results, DecisionType.PASS_WARNING)

    assert reason == "Warnings triggered: LOW_VOLUME_WARNING"


def test_validation_helpers_append_expected_results() -> None:
    results: list[FilterResult] = []
    config = {"allowed_symbols": ["BTCUSDT"], "allowed_timeframes": ["5m"]}
    signal = {"symbol": "ETHUSDT", "timeframe": "1h"}

    check_symbol(signal, config, results)
    check_timeframe(signal, config, results)

    assert [item.rule_code for item in results] == ["SYMBOL_ALLOWED", "TIMEFRAME_ALLOWED"]
    assert [item.result for item in results] == [RuleResult.FAIL, RuleResult.FAIL]
