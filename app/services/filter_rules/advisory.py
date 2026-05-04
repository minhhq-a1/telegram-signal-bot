"""
Advisory rules: volatility, cooldown, volume warnings, RR profile, backend score.
"""
from app.services.filter_rules.types import FilterResult
from app.core.enums import RuleResult, RuleSeverity


def check_volatility(signal: dict, config: dict, results: list[FilterResult]):
    """Check volatility regime and issue warnings for unfavorable conditions."""
    vol = signal.get("vol_regime")
    if vol == "RANGING_HIGH_VOL":
        results.append(FilterResult(
            "VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, -0.08
        ))
    elif vol == "SQUEEZE_BUILDING":
        results.append(FilterResult(
            "VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW, -0.03
        ))
    elif vol == "TRENDING_HIGH_VOL":
        results.append(FilterResult(
            "VOLATILITY_WARNING", "trading", RuleResult.PASS, RuleSeverity.INFO, 0.03
        ))
    else:
        results.append(FilterResult(
            "VOLATILITY_WARNING", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))


def check_cooldown(signal: dict, config: dict, signal_repo, results: list[FilterResult]):
    """Check if recent PASS_MAIN signal exists within cooldown window."""
    tf = signal.get("timeframe")
    cooldowns = config.get("cooldown_minutes", {
        "1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90
    })
    minutes = cooldowns.get(tf, 10)

    cands = signal_repo.find_recent_pass_main_same_side(
        symbol=signal["symbol"],
        timeframe=tf,
        side=signal["side"],
        since_minutes=minutes,
        exclude_signal_id=signal.get("signal_id"),
    )

    if len(cands) > 0:
        results.append(FilterResult(
            "COOLDOWN_ACTIVE", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, -0.10,
            {"count": len(cands)}
        ))
    else:
        results.append(FilterResult(
            "COOLDOWN_ACTIVE", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))


def check_low_volume(signal: dict, config: dict, results: list[FilterResult]):
    """Check volume ratio and warn if below normal levels."""
    vr = signal.get("vol_ratio")
    if vr is None or vr >= 1.0:
        results.append(FilterResult(
            "LOW_VOLUME_WARNING", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))
    elif vr < 0.8:
        results.append(FilterResult(
            "LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, -0.05
        ))
    else:  # 0.8 <= vr < 1.0
        results.append(FilterResult(
            "LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW
        ))


def check_rr_profile_match(signal: dict, config: dict, results: list[FilterResult]):
    """
    V1.1: RR profile match check.
    - RR outside target ± tolerance → WARN MEDIUM (pilot: not FAIL)
    - MIN_RR_REQUIRED maintains lower-bound check
    """
    rr = signal.get("risk_reward")
    if rr is None:
        return

    signal_type = signal.get("signal_type")
    targets = config.get("rr_target_by_type", {})
    tolerance = config.get("rr_tolerance_pct", 0.10)

    if signal_type not in targets:
        return  # Unknown type → skip, MIN_RR_REQUIRED already handled

    target = float(targets[signal_type])
    lo = target * (1 - tolerance)
    hi = target * (1 + tolerance)

    if lo <= rr <= hi:
        results.append(FilterResult(
            "RR_PROFILE_MATCH", "trading", RuleResult.PASS, RuleSeverity.INFO
        ))
    else:
        # Pilot mode: WARN MEDIUM, not FAIL
        details = {"rr": rr, "target": target, "tolerance_pct": tolerance, "lo": lo, "hi": hi}
        results.append(FilterResult(
            "RR_PROFILE_MATCH", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, 0.0, details
        ))


def check_backend_score(signal: dict, config: dict, results: list[FilterResult]):
    """
    V1.1: Backend rescoring + threshold.
    - Pilot mode: score < threshold → WARN MEDIUM (not FAIL)
    - Score >= threshold → PASS
    - Skip if 'rescoring' not in config (backward compat for existing tests)
    - Skip if signal_type not in rescoring config (legacy/partial payload)
    """
    if "rescoring" not in config:
        return  # V1.0 config — skip backend scoring

    signal_type = signal.get("signal_type")
    if signal_type not in config.get("rescoring", {}):
        return  # Unknown signal_type — skip backend scoring

    from app.services.rescoring_engine import rescore

    backend_score, items = rescore(signal, config)
    threshold = config.get("score_pass_threshold", 75)

    if backend_score < threshold:
        results.append(FilterResult(
            "BACKEND_SCORE_THRESHOLD", "rescoring", RuleResult.WARN, RuleSeverity.MEDIUM,
            0.0, {"score": backend_score, "threshold": threshold, "items": items},
        ))
    else:
        results.append(FilterResult(
            "BACKEND_SCORE_THRESHOLD", "rescoring", RuleResult.PASS, RuleSeverity.INFO,
            0.0, {"score": backend_score, "threshold": threshold, "items": items},
        ))


