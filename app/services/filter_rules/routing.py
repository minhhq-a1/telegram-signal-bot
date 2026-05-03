"""
Routing rules: symbol and timeframe allowlists.
"""
from app.services.filter_rules.types import FilterResult
from app.core.enums import RuleResult, RuleSeverity


def check_symbol(signal: dict, config: dict, results: list[FilterResult]):
    """Check if symbol is in allowed list."""
    allowed = config.get("allowed_symbols", ["BTCUSDT", "BTCUSD"])
    if signal["symbol"] not in allowed:
        results.append(FilterResult(
            "SYMBOL_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL,
            0.0, {"allowed": allowed}
        ))
    else:
        results.append(FilterResult(
            "SYMBOL_ALLOWED", "validation", RuleResult.PASS, RuleSeverity.INFO
        ))


def check_timeframe(signal: dict, config: dict, results: list[FilterResult]):
    """Check if timeframe is in allowed list."""
    allowed = config.get("allowed_timeframes", ["1m", "3m", "5m", "12m", "15m", "30m", "1h"])
    if signal["timeframe"] not in allowed:
        results.append(FilterResult(
            "TIMEFRAME_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL,
            0.0, {"allowed": allowed}
        ))
    else:
        results.append(FilterResult(
            "TIMEFRAME_ALLOWED", "validation", RuleResult.PASS, RuleSeverity.INFO
        ))
