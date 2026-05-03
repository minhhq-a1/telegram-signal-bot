"""
Routing rules: decision logic and route determination.
"""
from app.services.filter_rules.types import FilterResult
from app.core.enums import RuleResult, RuleSeverity, DecisionType, TelegramRoute


def decide(results: list[FilterResult]) -> tuple[DecisionType, TelegramRoute]:
    """Determine decision and route based on filter results."""
    if any(result.result == RuleResult.FAIL for result in results):
        return DecisionType.REJECT, TelegramRoute.NONE

    significant_warns = [
        result
        for result in results
        if result.result == RuleResult.WARN
        and result.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
    ]
    if significant_warns:
        return DecisionType.PASS_WARNING, TelegramRoute.WARN

    return DecisionType.PASS_MAIN, TelegramRoute.MAIN


def build_decision_reason(
    phase_reason: str,
    results: list[FilterResult],
    decision: DecisionType,
) -> str:
    """Build human-readable decision reason from filter results."""
    fail_codes = [result.rule_code for result in results if result.result == RuleResult.FAIL]
    medium_plus_warn_codes = [
        result.rule_code
        for result in results
        if result.result == RuleResult.WARN and result.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
    ]
    low_warn_codes = [
        result.rule_code
        for result in results
        if result.result == RuleResult.WARN and result.severity == RuleSeverity.LOW
    ]

    if decision == DecisionType.REJECT:
        return f"{phase_reason}: {', '.join(fail_codes)}"
    if decision == DecisionType.PASS_WARNING:
        return f"Warnings triggered: {', '.join(medium_plus_warn_codes)}"
    if low_warn_codes:
        return f"Passed main route with advisory warnings: {', '.join(low_warn_codes)}"
    return "Passed all filters"
