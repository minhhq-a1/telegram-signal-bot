"""
Business rules: confidence thresholds, duplicate suppression, news blocks, regime blocks.
"""
from datetime import datetime, timezone
from app.services.filter_rules.types import FilterResult
from app.core.enums import RuleResult, RuleSeverity


def check_min_confidence_by_tf(signal: dict, config: dict, results: list[FilterResult]):
    """Check if confidence meets timeframe-specific threshold."""
    tf = signal.get("timeframe")
    conf = signal.get("indicator_confidence", 0)
    thresholds = config.get("confidence_thresholds", {
        "1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70
    })
    threshold = thresholds.get(tf, 0.85)

    if conf >= threshold:
        results.append(FilterResult(
            "MIN_CONFIDENCE_BY_TF", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))
    else:
        results.append(FilterResult(
            "MIN_CONFIDENCE_BY_TF", "trading", RuleResult.FAIL, RuleSeverity.HIGH,
            0.0, {"confidence": conf, "threshold": threshold}
        ))


def check_duplicate(signal: dict, config: dict, signal_repo, results: list[FilterResult]):
    """Check for duplicate signals within cooldown window and price tolerance."""
    tf = signal.get("timeframe")
    cooldowns = config.get("cooldown_minutes", {
        "1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90
    })
    minutes = cooldowns.get(tf, 10)
    tolerance = config.get("duplicate_price_tolerance_pct", 0.002)

    candidates = signal_repo.find_recent_similar_by_entry_range(
        symbol=signal["symbol"],
        timeframe=tf,
        side=signal["side"],
        signal_type=signal.get("signal_type"),
        entry_price=signal.get("entry_price", 0),
        tolerance_pct=tolerance,
        since_minutes=minutes,
        exclude_signal_id=signal.get("signal_id"),
    )

    if candidates:
        results.append(FilterResult(
            "DUPLICATE_SUPPRESSION", "trading", RuleResult.FAIL, RuleSeverity.HIGH
        ))
    else:
        results.append(FilterResult(
            "DUPLICATE_SUPPRESSION", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))


def check_news_block(signal: dict, config: dict, market_event_repo, results: list[FilterResult]):
    """Check if signal falls within news event block window."""
    if not config.get("enable_news_block", True):
        return

    db_time = datetime.now(timezone.utc)
    if signal.get("payload_timestamp"):
        db_time = signal["payload_timestamp"]

    before_min = config.get("news_block_before_min", 15)
    after_min = config.get("news_block_after_min", 30)

    events = market_event_repo.find_active_around(db_time, before_min, after_min)
    if events:
        results.append(FilterResult(
            "NEWS_BLOCK", "trading", RuleResult.FAIL, RuleSeverity.HIGH,
            0.0, {"active_events": len(events)}
        ))
    else:
        results.append(FilterResult(
            "NEWS_BLOCK", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))


def check_regime_hard_block(signal: dict, config: dict, results: list[FilterResult]):
    """Check for regime/direction mismatch (LONG in STRONG_TREND_DOWN, etc)."""
    side = signal.get("side")
    regime = signal.get("regime")

    if side == "LONG" and regime == "STRONG_TREND_DOWN":
        results.append(FilterResult(
            "REGIME_HARD_BLOCK", "trading", RuleResult.FAIL, RuleSeverity.HIGH
        ))
    elif side == "SHORT" and regime == "STRONG_TREND_UP":
        results.append(FilterResult(
            "REGIME_HARD_BLOCK", "trading", RuleResult.FAIL, RuleSeverity.HIGH
        ))
    else:
        results.append(FilterResult(
            "REGIME_HARD_BLOCK", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))
