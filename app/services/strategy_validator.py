from __future__ import annotations
from app.services.filter_engine import FilterResult
from app.core.enums import RuleResult, RuleSeverity


_GROUP = "strategy"


def _pass(code: str) -> FilterResult:
    return FilterResult(code, _GROUP, RuleResult.PASS, RuleSeverity.INFO)


def _fail(code: str, details: dict | None = None) -> FilterResult:
    return FilterResult(code, _GROUP, RuleResult.FAIL, RuleSeverity.HIGH, 0.0, details)


def _warn(code: str, details: dict | None = None) -> FilterResult:
    # Pilot: quality floor rules = WARN MEDIUM (not FAIL)
    return FilterResult(code, _GROUP, RuleResult.WARN, RuleSeverity.MEDIUM, 0.0, details)


def validate_strategy(signal: dict, config: dict) -> list[FilterResult]:
    signal_type = signal.get("signal_type")
    if signal_type == "SHORT_SQUEEZE":
        return _validate_short_squeeze(signal, config)
    if signal_type == "SHORT_V73":
        return _validate_short_v73(signal, config)
    if signal_type == "LONG_V73":
        return _validate_long_v73(signal, config)
    return []


def _validate_short_squeeze(signal: dict, config: dict) -> list[FilterResult]:
    th = config.get("strategy_thresholds", {}).get("SHORT_SQUEEZE", {})
    out: list[FilterResult] = []

    # squeeze_fired: Pine sends int (0/1), ORM is bool → check both
    squeeze_fired = signal.get("squeeze_fired")
    squeeze_ok = squeeze_fired in (1, True)
    out.append(_fail("SQ_NO_FIRED") if not squeeze_ok else _pass("SQ_NO_FIRED"))

    # mom_direction: Pine sends int (-1/0/1), SHORT_SQUEEZE requires -1
    mom = signal.get("mom_direction")
    out.append(
        _fail("SQ_BAD_MOM_DIRECTION", {"mom_direction": mom}) if mom != -1 else _pass("SQ_BAD_MOM_DIRECTION")
    )

    # vol_regime must be BREAKOUT_IMMINENT
    vol_regime = signal.get("vol_regime")
    out.append(
        _fail("SQ_BAD_VOL_REGIME", {"vol_regime": vol_regime})
        if vol_regime != "BREAKOUT_IMMINENT"
        else _pass("SQ_BAD_VOL_REGIME")
    )

    # strategy must be KELTNER_SQUEEZE
    strategy = signal.get("strategy")
    out.append(
        _fail("SQ_BAD_STRATEGY_NAME", {"strategy": strategy})
        if strategy != "KELTNER_SQUEEZE"
        else _pass("SQ_BAD_STRATEGY_NAME")
    )

    # Quality floor: RSI >= rsi_min → WARN if lower
    rsi = signal.get("rsi")
    rsi_min = th.get("rsi_min", 35)
    if rsi is not None and rsi < rsi_min:
        out.append(_warn("SQ_RSI_FLOOR", {"rsi": rsi, "min": rsi_min}))
    else:
        out.append(_pass("SQ_RSI_FLOOR"))

    # Quality floor: kc_position <= kc_position_max → WARN if higher
    kc = signal.get("kc_position")
    kc_max = th.get("kc_position_max", 0.55)
    if kc is not None and kc > kc_max:
        out.append(_warn("SQ_KC_POSITION_FLOOR", {"kc_position": kc, "max": kc_max}))
    else:
        out.append(_pass("SQ_KC_POSITION_FLOOR"))

    # Quality floor: rsi_slope must be <= rsi_slope_max (more negative = steeper RSI decline is better)
    # e.g. rsi_slope_max = -2 means RSI must be declining by at least 2 units; -1 is too flat → WARN
    rsi_slope = signal.get("rsi_slope")
    rsi_slope_max = th.get("rsi_slope_max", -2)
    if rsi_slope is not None and rsi_slope > rsi_slope_max:
        out.append(_warn("SQ_RSI_SLOPE_FLOOR", {"rsi_slope": rsi_slope, "max": rsi_slope_max}))
    else:
        out.append(_pass("SQ_RSI_SLOPE_FLOOR"))

    return out


def _validate_short_v73(signal: dict, config: dict) -> list[FilterResult]:
    th = config.get("strategy_thresholds", {}).get("SHORT_V73", {})
    out: list[FilterResult] = []

    out.append(
        _fail("S_BASE_BAD_STRATEGY_NAME", {"strategy": signal.get("strategy")})
        if signal.get("strategy") != "RSI_STOCH_V73"
        else _pass("S_BASE_BAD_STRATEGY_NAME")
    )

    # RSI floor: SHORT_V73 needs RSI >= rsi_min → WARN if lower
    rsi = signal.get("rsi")
    rsi_min = th.get("rsi_min", 60)
    if rsi is not None and rsi < rsi_min:
        out.append(_warn("S_BASE_RSI_FLOOR", {"rsi": rsi, "min": rsi_min}))
    else:
        out.append(_pass("S_BASE_RSI_FLOOR"))

    # Stoch floor: SHORT_V73 needs stoch_k >= stoch_k_min → WARN if lower
    stoch = signal.get("stoch_k")
    stoch_min = th.get("stoch_k_min", 70)
    if stoch is not None and stoch < stoch_min:
        out.append(_warn("S_BASE_STOCH_FLOOR", {"stoch_k": stoch, "min": stoch_min}))
    else:
        out.append(_pass("S_BASE_STOCH_FLOOR"))

    return out


def _validate_long_v73(signal: dict, config: dict) -> list[FilterResult]:
    th = config.get("strategy_thresholds", {}).get("LONG_V73", {})
    out: list[FilterResult] = []

    out.append(
        _fail("L_BASE_BAD_STRATEGY_NAME", {"strategy": signal.get("strategy")})
        if signal.get("strategy") != "RSI_STOCH_V73"
        else _pass("L_BASE_BAD_STRATEGY_NAME")
    )

    # RSI floor: LONG_V73 needs RSI <= rsi_max → WARN if higher
    rsi = signal.get("rsi")
    rsi_max = th.get("rsi_max", 35)
    if rsi is not None and rsi > rsi_max:
        out.append(_warn("L_BASE_RSI_FLOOR", {"rsi": rsi, "max": rsi_max}))
    else:
        out.append(_pass("L_BASE_RSI_FLOOR"))

    # Stoch floor: LONG_V73 needs stoch_k <= stoch_k_max → WARN if higher
    stoch = signal.get("stoch_k")
    stoch_max = th.get("stoch_k_max", 20)
    if stoch is not None and stoch > stoch_max:
        out.append(_warn("L_BASE_STOCH_FLOOR", {"stoch_k": stoch, "max": stoch_max}))
    else:
        out.append(_pass("L_BASE_STOCH_FLOOR"))

    return out
