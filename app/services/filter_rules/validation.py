"""
Validation rules: symbol, timeframe, confidence range and price validity checks.
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


def check_confidence_range(signal: dict, config: dict, results: list[FilterResult]):
    """Check if indicator_confidence is in valid range [0.0, 1.0]."""
    conf = signal.get("indicator_confidence", -1)
    if 0.0 <= conf <= 1.0:
        results.append(FilterResult(
            "CONFIDENCE_RANGE_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO
        ))
    else:
        results.append(FilterResult(
            "CONFIDENCE_RANGE_VALID", "validation", RuleResult.FAIL, RuleSeverity.HIGH,
            0.0, {"confidence": conf}
        ))


def check_price_valid(signal: dict, config: dict, results: list[FilterResult]):
    """Check if all price fields are positive."""
    price = signal.get("price", 0)
    entry = signal.get("entry_price", 0)
    sl = signal.get("stop_loss") or 0
    tp = signal.get("take_profit") or 0
    if price > 0 and entry > 0 and sl > 0 and tp > 0:
        results.append(FilterResult(
            "PRICE_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO
        ))
    else:
        results.append(FilterResult(
            "PRICE_VALID", "validation", RuleResult.FAIL, RuleSeverity.HIGH
        ))
