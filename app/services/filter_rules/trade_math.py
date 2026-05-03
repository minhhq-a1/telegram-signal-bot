"""
Trade math rules: direction sanity and minimum risk/reward checks.
"""
from app.services.filter_rules.types import FilterResult
from app.core.enums import RuleResult, RuleSeverity


def check_direction_sanity(signal: dict, config: dict, results: list[FilterResult]):
    """Check if entry/SL/TP ordering matches trade direction."""
    entry = signal.get("entry_price", 0)
    sl = signal.get("stop_loss", 0)
    tp = signal.get("take_profit", 0)
    side = signal.get("side")

    is_valid = False
    if side == "LONG":
        if sl < entry and entry < tp:
            is_valid = True
    elif side == "SHORT":
        if tp < entry and entry < sl:
            is_valid = True

    if is_valid:
        results.append(FilterResult(
            "DIRECTION_SANITY_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO
        ))
    else:
        results.append(FilterResult(
            "DIRECTION_SANITY_VALID", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL
        ))


def check_min_rr(signal: dict, config: dict, results: list[FilterResult]):
    """Check if risk/reward meets minimum threshold (base or squeeze)."""
    rr = signal.get("risk_reward")
    if rr is None or rr <= 0:
        results.append(FilterResult(
            "MIN_RR_REQUIRED", "trading", RuleResult.FAIL, RuleSeverity.HIGH,
            0.0, {"rr": rr}
        ))
        return

    signal_type = signal.get("signal_type")
    if signal_type == "SHORT_SQUEEZE":
        min_rr = config.get("rr_min_squeeze", 2.0)
    else:
        min_rr = config.get("rr_min_base", 1.5)

    if rr >= min_rr:
        results.append(FilterResult(
            "MIN_RR_REQUIRED", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))
    else:
        results.append(FilterResult(
            "MIN_RR_REQUIRED", "trading", RuleResult.FAIL, RuleSeverity.HIGH,
            0.0, {"rr": rr, "min_required": min_rr}
        ))
