from __future__ import annotations


def rescore(signal: dict, config: dict) -> tuple[int, list[str]]:
    """Return (final_score_0_to_100, breakdown_items_as_strings)."""
    signal_type = signal.get("signal_type")
    rs_cfg = config.get("rescoring", {}).get(signal_type)
    if not rs_cfg:
        return 70, ["base_fallback=70"]

    score = int(rs_cfg.get("base", 70))
    items: list[str] = [f"base={score}"]
    bonuses = rs_cfg.get("bonuses", {})
    penalties = rs_cfg.get("penalties", {})

    applied = _collect_applied_rules(signal)

    for key, delta in bonuses.items():
        if key in applied:
            score += int(delta)
            items.append(f"{key}+{delta}")

    for key, delta in penalties.items():
        if key in applied:
            score += int(delta)
            items.append(f"{key}{delta}")

    score = max(0, min(100, score))
    return score, items


def _collect_applied_rules(signal: dict) -> set[str]:
    rules: set[str] = set()

    conf = _num(signal.get("indicator_confidence"))
    regime = signal.get("regime")
    vol_regime = signal.get("vol_regime")
    mom = signal.get("mom_direction")
    squeeze_bars = _num(signal.get("squeeze_bars"))
    rsi = _num(signal.get("rsi"))
    rsi_slope = _num(signal.get("rsi_slope"))
    stoch_k = _num(signal.get("stoch_k"))
    atr_percentile = _num(signal.get("atr_percentile"))
    kc = _num(signal.get("kc_position"))
    atr_pct = _num(signal.get("atr_pct"))

    if vol_regime == "BREAKOUT_IMMINENT":
        rules.add("vol_regime_breakout_imminent")

    if regime == "WEAK_TREND_DOWN":
        rules.add("regime_weak_trend_down")
        rules.add("regime_trend_down")
    if regime == "STRONG_TREND_DOWN":
        rules.add("regime_strong_trend_down")
        rules.add("regime_trend_down")
    if regime == "WEAK_TREND_UP":
        rules.add("regime_weak_trend_up")
        rules.add("regime_trend_up")
    if regime == "STRONG_TREND_UP":
        rules.add("regime_strong_trend_up")
        rules.add("regime_trend_up")

    if vol_regime == "RANGING_HIGH_VOL":
        rules.add("vol_ranging_high")

    if mom == -1:
        rules.add("mom_direction_neg1")

    if squeeze_bars is not None:
        if squeeze_bars >= 4:
            rules.add("squeeze_bars_ge_4")
        if squeeze_bars >= 6:
            rules.add("squeeze_bars_ge_6")

    if rsi is not None:
        if rsi >= 40:
            rules.add("rsi_ge_40")
        if rsi < 35:
            rules.add("rsi_lt_35")
        if rsi >= 70:
            rules.add("rsi_ge_70")
        if rsi <= 25:
            rules.add("rsi_le_25")

    if rsi_slope is not None:
        if rsi_slope <= -4:
            rules.add("rsi_slope_le_neg4")
        if rsi_slope >= 2:
            rules.add("rsi_slope_ge_2")

    if stoch_k is not None:
        if stoch_k >= 85:
            rules.add("stoch_ge_85")
        if stoch_k <= 10:
            rules.add("stoch_le_10")

    if atr_percentile is not None and atr_percentile >= 70:
        rules.add("atr_percentile_ge_70")

    if kc is not None and kc <= 0.40:
        rules.add("kc_position_le_040")

    if atr_pct is not None:
        if atr_pct < 0.20:
            rules.add("atr_pct_lt_020")
        if atr_pct > 1.50:
            rules.add("atr_pct_gt_150")

    if conf is not None and conf >= 0.90:
        rules.add("confidence_ge_090")

    return rules


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
