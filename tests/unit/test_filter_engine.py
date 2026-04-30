from unittest.mock import MagicMock
from app.services.filter_engine import FilterEngine

def make_filter_engine(config_overrides=None):
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m","3m","5m","12m","15m","30m","1h"],
        "confidence_thresholds": {"5m": 0.78, "30m": 0.72, "1h": 0.70},
        "cooldown_minutes": {"5m": 10, "30m": 45, "1h": 90},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
        "enable_news_block": True,
        "news_block_before_min": 15,
        "news_block_after_min": 30,
        "rr_tolerance_pct": 0.10,
        "rr_target_by_type": {
            "SHORT_SQUEEZE": 2.5,
            "SHORT_V73": 1.67,
            "LONG_V73": 1.67,
        },
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {
                "rsi_min": 35,
                "rsi_slope_max": -2,
                "kc_position_max": 0.55,
                "atr_pct_min": 0.20,
            },
            "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
            "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
        },
        "rescoring": {},
        "score_pass_threshold": 75,
    }
    if config_overrides:
        config.update(config_overrides)

    mock_signal_repo = MagicMock()
    mock_signal_repo.find_recent_pass_main_same_side.return_value = []
    mock_signal_repo.find_recent_similar.return_value = []
    mock_signal_repo.find_recent_similar_by_entry_range.return_value = []

    mock_market_event_repo = MagicMock()
    mock_market_event_repo.find_active_around.return_value = []

    return FilterEngine(config, mock_signal_repo, mock_market_event_repo)

def make_signal(**overrides):
    base = {
        "signal_id": "test-001",
        "side": "LONG",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "price": 68250.5,
        "entry_price": 68250.5,
        "stop_loss": 67980.0,
        "take_profit": 68740.0,
        "risk_reward": 1.81,
        "indicator_confidence": 0.82,
        "signal_type": "LONG_V73",
        "strategy": "RSI_STOCH_V73",  # V1.1: strategy field required for strategy validator
        "regime": "WEAK_TREND_DOWN",
        "vol_regime": "TRENDING_LOW_VOL",
        "vol_ratio": 1.24,
    }
    base.update(overrides)
    return base

# Test 1: Happy path — không FAIL, không WARN MEDIUM+ → PASS_MAIN
def test_pass_main():
    engine = make_filter_engine()
    result = engine.run(make_signal())
    assert result.final_decision == "PASS_MAIN"
    assert result.route == "MAIN"
    assert 0.0 <= result.server_score <= 1.0  # tính được nhưng không dùng để route

# Test 2: Confidence too low → FAIL → REJECT
def test_reject_low_confidence():
    engine = make_filter_engine()
    result = engine.run(make_signal(indicator_confidence=0.75))
    assert result.final_decision == "REJECT"
    assert result.route == "NONE"
    assert result.decision_reason == "Business rule failed: MIN_CONFIDENCE_BY_TF"
    fail_rules = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "MIN_CONFIDENCE_BY_TF" in fail_rules

# Test 3: Payload regime hard block remains a V1 rule.
def test_reject_strong_downtrend_long():
    engine = make_filter_engine()
    result = engine.run(make_signal(regime="STRONG_TREND_DOWN"))
    assert result.final_decision == "REJECT"
    assert result.route == "NONE"

# Test 4: RANGING_HIGH_VOL → WARN MEDIUM → PASS_WARNING (không reject)
# Boolean gate key insight: RANGING_HIGH_VOL không làm REJECT, chỉ downgrade channel
def test_ranging_high_vol_routes_to_warning_not_reject():
    engine = make_filter_engine()
    result = engine.run(make_signal(vol_regime="RANGING_HIGH_VOL"))
    assert result.final_decision == "PASS_WARNING"  # WARN MEDIUM → warning
    assert result.route == "WARN"
    assert result.decision_reason == "Warnings triggered: VOLATILITY_WARNING"
    # server_score giảm vì -0.08 delta, nhưng không quyết định route
    warn_rules = [r.rule_code for r in result.filter_results if r.result.value == "WARN"]
    assert "VOLATILITY_WARNING" in warn_rules

# Test 5: Unsupported symbol → FAIL → REJECT
def test_reject_unsupported_symbol():
    engine = make_filter_engine()
    result = engine.run(make_signal(symbol="ETHUSDT"))
    assert result.final_decision == "REJECT"

# Test 6: Cooldown chỉ route warning khi có prior PASS_MAIN
def test_cooldown_pass_main_routes_to_warning():
    engine = make_filter_engine()
    engine.signal_repo.find_recent_pass_main_same_side.return_value = [MagicMock()]
    # Dù confidence = 0.99, cooldown WARN MEDIUM vẫn downgrade
    result = engine.run(make_signal(indicator_confidence=0.99))
    assert result.final_decision == "PASS_WARNING"
    assert result.route == "WARN"


def test_cooldown_ignores_non_pass_main_history():
    engine = make_filter_engine()
    engine.signal_repo.find_recent_pass_main_same_side.return_value = []
    result = engine.run(make_signal(indicator_confidence=0.99))
    assert result.final_decision == "PASS_MAIN"
    assert result.route == "MAIN"

# Test 7: RR too low → FAIL → REJECT
def test_reject_low_rr():
    engine = make_filter_engine()
    result = engine.run(make_signal(risk_reward=1.2))
    assert result.final_decision == "REJECT"

# Test 8: Squeeze trade cần rr_min_squeeze=2.0
def test_squeeze_requires_higher_rr():
    engine = make_filter_engine()
    # rr=1.8 đủ cho base (>=1.5) nhưng không đủ cho squeeze (>=2.0)
    result = engine.run(make_signal(
        signal_type="SHORT_SQUEEZE", side="SHORT",
        entry_price=68910.0, stop_loss=69200.0,
        take_profit=68400.0, risk_reward=1.76
    ))
    assert result.final_decision == "REJECT"
    fail_rules = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "MIN_RR_REQUIRED" in fail_rules

# Test 9: SQUEEZE_BUILDING (WARN LOW) không downgrade sang WARNING
# WARN LOW không đủ để route sang WARN channel
def test_squeeze_building_stays_main():
    engine = make_filter_engine()
    result = engine.run(make_signal(vol_regime="SQUEEZE_BUILDING"))
    assert result.final_decision == "PASS_MAIN"  # WARN LOW → vẫn MAIN
    assert result.route == "MAIN"
    assert result.decision_reason == "Passed main route with advisory warnings: VOLATILITY_WARNING"

# Test 10: server_score được tính đúng (analytics check)
def test_server_score_calculated_for_analytics():
    engine = make_filter_engine()
    # RANGING_HIGH_VOL có score_delta=-0.08
    result = engine.run(make_signal(
        indicator_confidence=0.82,
        vol_regime="RANGING_HIGH_VOL"
    ))
    # server_score = 0.82 + (-0.08) = 0.74
    assert abs(result.server_score - 0.74) < 0.01
    # Nhưng decision là PASS_WARNING (WARN MEDIUM present), không phải REJECT
    assert result.final_decision == "PASS_WARNING"


def test_duplicate_tolerance_uses_fractional_0_2_percent_boundary():
    engine = make_filter_engine()

    near_match = MagicMock()
    near_match.entry_price = 68251.0  # ~0.00073 away from 68200, inside 0.2%
    engine.signal_repo.find_recent_similar_by_entry_range.return_value = [near_match]

    result = engine.run(
        make_signal(
            entry_price=68200.0,
            price=68200.0,
            take_profit=68690.0,
            stop_loss=67930.0,
        )
    )
    assert result.final_decision == "REJECT"
    fail_rules = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "DUPLICATE_SUPPRESSION" in fail_rules


def test_duplicate_tolerance_does_not_reject_outside_0_2_percent_boundary():
    engine = make_filter_engine()

    far_enough = MagicMock()
    far_enough.entry_price = 68350.0  # ~0.0022 away from 68200, outside 0.2%
    engine.signal_repo.find_recent_similar_by_entry_range.return_value = []

    result = engine.run(
        make_signal(
            entry_price=68200.0,
            price=68200.0,
            take_profit=68690.0,
            stop_loss=67930.0,
        )
    )
    assert result.final_decision == "PASS_MAIN"


def test_news_block_can_be_disabled_via_snake_case_config():
    engine = make_filter_engine({"enable_news_block": False})
    engine.market_event_repo.find_active_around.return_value = [MagicMock()]

    result = engine.run(make_signal())

    assert result.final_decision == "PASS_MAIN"
    rule_codes = [r.rule_code for r in result.filter_results]
    assert "NEWS_BLOCK" not in rule_codes


def test_pass_main_without_warnings_has_clear_reason():
    engine = make_filter_engine()

    result = engine.run(make_signal())

    assert result.decision_reason == "Passed all filters"


def test_30m_timeframe_is_allowed_with_its_threshold():
    engine = make_filter_engine()

    result = engine.run(make_signal(timeframe="30m", indicator_confidence=0.72))

    assert result.final_decision == "PASS_MAIN"


def test_1h_timeframe_is_allowed_with_its_threshold():
    engine = make_filter_engine()

    result = engine.run(make_signal(timeframe="1h", indicator_confidence=0.70))

    assert result.final_decision == "PASS_MAIN"


# =============================================================================
# V1.1 Integration Tests
# =============================================================================

def _v11_config():
    return {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m","3m","5m","12m","15m","30m","1h"],
        "confidence_thresholds": {"5m": 0.78},
        "cooldown_minutes": {"5m": 10},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
        "enable_news_block": False,
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
            "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
            "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
        },
        "rescoring": {
            "SHORT_SQUEEZE": {
                "base": 70,
                "bonuses": {
                    "vol_regime_breakout_imminent": 8,
                    "regime_weak_trend_down": 6,
                    "mom_direction_neg1": 5,
                    "squeeze_bars_ge_6": 5,
                    "rsi_ge_40": 4,
                    "rsi_slope_le_neg4": 4,
                    "atr_percentile_ge_70": 3,
                    "kc_position_le_040": 3,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "rsi_lt_35": -8,
                    "atr_pct_lt_020": -8,
                },
            },
            "SHORT_V73": {
                "base": 72,
                "bonuses": {
                    "rsi_ge_70": 5,
                    "stoch_ge_85": 5,
                    "rsi_slope_le_neg4": 4,
                    "regime_trend_down": 6,
                    "confidence_ge_090": 3,
                },
                "penalties": {},
            },
            "LONG_V73": {
                "base": 72,
                "bonuses": {
                    "rsi_le_25": 5,
                    "stoch_le_10": 5,
                    "rsi_slope_ge_2": 4,
                    "regime_trend_up": 6,
                    "confidence_ge_090": 3,
                },
                "penalties": {},
            },
        },
        "score_pass_threshold": 75,
        "rr_tolerance_pct": 0.10,
        "rr_target_by_type": {"SHORT_SQUEEZE": 2.5, "SHORT_V73": 1.67, "LONG_V73": 1.67},
    }


def _v11_signal(**overrides):
    base = {
        "signal_id": "v11-001",
        "side": "SHORT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "price": 74988.60,
        "entry_price": 74988.60,
        "stop_loss": 75429.33,
        "take_profit": 73886.79,
        "risk_reward": 2.5,
        "indicator_confidence": 0.90,
        "signal_type": "SHORT_SQUEEZE",
        "strategy": "KELTNER_SQUEEZE",
        "regime": "WEAK_TREND_DOWN",
        "vol_regime": "BREAKOUT_IMMINENT",
        "squeeze_fired": 1,
        "mom_direction": -1,
        "rsi": 37.5,
        "rsi_slope": -5.7,
        "kc_position": 0.31,
        "atr_pct": 0.49,
        "atr_percentile": 78.0,
        "squeeze_bars": 6,
        "vol_ratio": 1.24,
    }
    base.update(overrides)
    return base


def test_v11_short_squeeze_pass_main():
    """SHORT_SQUEEZE ideal signal → PASS_MAIN (no FAIL, no WARN MEDIUM+)"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal())
    assert result.final_decision.value == "PASS_MAIN"
    assert result.route.value == "MAIN"


def test_v11_sq_no_fired_reject():
    """squeeze_fired=0 → SQ_NO_FIRED FAIL → REJECT"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(squeeze_fired=0))
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "SQ_NO_FIRED" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_v11_sq_bad_mom_direction_reject():
    """mom_direction=1 → SQ_BAD_MOM_DIRECTION FAIL → REJECT"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(mom_direction=1))
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "SQ_BAD_MOM_DIRECTION" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_v11_sq_bad_vol_regime_reject():
    """vol_regime != BREAKOUT_IMMINENT → SQ_BAD_VOL_REGIME FAIL → REJECT"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(vol_regime="TRENDING_LOW_VOL"))
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "SQ_BAD_VOL_REGIME" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_v11_sq_bad_strategy_reject():
    """strategy != KELTNER_SQUEEZE → SQ_BAD_STRATEGY_NAME FAIL → REJECT"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(strategy="RSI_STOCH_V73"))
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "SQ_BAD_STRATEGY_NAME" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_v11_sq_rsi_floor_warns():
    """rsi=30 < rsi_min(35) → SQ_RSI_FLOOR WARN → PASS_WARNING (pilot)"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(rsi=30))
    codes = {r.rule_code: r for r in result.filter_results}
    assert codes["SQ_RSI_FLOOR"].result.value == "WARN"
    assert codes["SQ_RSI_FLOOR"].severity.value == "MEDIUM"
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_sq_kc_position_warns():
    """kc_position=0.80 > kc_position_max(0.55) → WARN → PASS_WARNING"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(kc_position=0.80))
    codes = {r.rule_code: r for r in result.filter_results}
    assert codes["SQ_KC_POSITION_FLOOR"].result.value == "WARN"
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_backend_score_threshold_warns():
    """Backend score < threshold → BACKEND_SCORE_THRESHOLD WARN (pilot)"""
    cfg = _v11_config()
    # Set threshold > max possible score (100) so ANY signal triggers WARN
    cfg["score_pass_threshold"] = 200
    engine = make_filter_engine(cfg)
    # All ideal SHORT_SQUEEZE params → score=100, still < 200 → WARN
    result = engine.run(_v11_signal())
    score_rule = next((r for r in result.filter_results if r.rule_code == "BACKEND_SCORE_THRESHOLD"), None)
    assert score_rule is not None
    assert score_rule.result.value == "WARN"
    assert score_rule.severity.value == "MEDIUM"
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_backend_score_passes():
    """Backend score >= threshold → BACKEND_SCORE_THRESHOLD PASS"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal())
    score_rule = next((r for r in result.filter_results if r.rule_code == "BACKEND_SCORE_THRESHOLD"), None)
    assert score_rule is not None
    assert score_rule.result.value == "PASS"


def test_v11_rr_profile_match_warns_upper_bound():
    """RR=3.0 > target(2.5)+10%(2.75) → RR_PROFILE_MATCH WARN → PASS_WARNING (pilot)"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(
        entry_price=100.0, stop_loss=101.0, take_profit=97.0, risk_reward=3.0
    ))
    rr_rule = next((r for r in result.filter_results if r.rule_code == "RR_PROFILE_MATCH"), None)
    assert rr_rule is not None
    assert rr_rule.result.value == "WARN"
    assert rr_rule.severity.value == "MEDIUM"
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_min_rr_still_enforces_lower_bound():
    """MIN_RR_REQUIRED (lower-bound) vẫn FAIL nếu RR quá thấp"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(
        entry_price=100.0, stop_loss=101.0, take_profit=100.8, risk_reward=0.8
    ))
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "MIN_RR_REQUIRED" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_v11_short_v73_pass():
    """SHORT_V73 ideal signal → PASS_MAIN"""
    engine = make_filter_engine(_v11_config())
    # SHORT: tp < entry < sl
    # RR=1.67 exactly → within target±10% band [1.50, 1.84]
    result = engine.run(_v11_signal(
        signal_type="SHORT_V73", strategy="RSI_STOCH_V73",
        rsi=72, stoch_k=80,
        entry_price=100.0, stop_loss=101.0, take_profit=97.0, risk_reward=1.67,
        squeeze_fired=0, mom_direction=0, vol_regime="TRENDING_LOW_VOL",
    ))
    assert result.final_decision.value == "PASS_MAIN"


def test_v11_short_v73_rsi_floor_warns():
    """SHORT_V73 rsi=55 < rsi_min(60) → WARN"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(
        signal_type="SHORT_V73", strategy="RSI_STOCH_V73",
        rsi=55, stoch_k=80,
        entry_price=100.0, stop_loss=101.0, take_profit=97.0, risk_reward=1.67,
        squeeze_fired=0, mom_direction=0, vol_regime="TRENDING_LOW_VOL",
    ))
    codes = {r.rule_code: r for r in result.filter_results}
    assert codes["S_BASE_RSI_FLOOR"].result.value == "WARN"
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_long_v73_pass():
    """LONG_V73 ideal signal → PASS_MAIN"""
    engine = make_filter_engine(_v11_config())
    # LONG: sl < entry < tp
    # RR=1.67 exactly → within target±10% band [1.50, 1.84]
    result = engine.run(_v11_signal(
        side="LONG", signal_type="LONG_V73", strategy="RSI_STOCH_V73",
        rsi=28, stoch_k=15,
        entry_price=100.0, stop_loss=98.4, take_profit=101.67, risk_reward=1.67,
        squeeze_fired=0, mom_direction=0, vol_regime="TRENDING_LOW_VOL",
    ))
    assert result.final_decision.value == "PASS_MAIN"


def test_v11_long_v73_rsi_floor_warns():
    """LONG_V73 rsi=41 > rsi_max(35) → WARN"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(
        side="LONG", signal_type="LONG_V73", strategy="RSI_STOCH_V73",
        rsi=41, stoch_k=15,
        entry_price=100.0, stop_loss=98.4, take_profit=101.67, risk_reward=1.67,
        squeeze_fired=0, mom_direction=0, vol_regime="TRENDING_LOW_VOL",
    ))
    codes = {r.rule_code: r for r in result.filter_results}
    assert codes["L_BASE_RSI_FLOOR"].result.value == "WARN"
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_multiple_strategy_warns_downgrade_to_warning():
    """Multiple WARN MEDIUM rules → still PASS_WARNING (not REJECT)"""
    engine = make_filter_engine(_v11_config())
    result = engine.run(_v11_signal(rsi=30, kc_position=0.80))
    warn_codes = [r.rule_code for r in result.filter_results if r.result.value == "WARN"]
    assert "SQ_RSI_FLOOR" in warn_codes
    assert "SQ_KC_POSITION_FLOOR" in warn_codes
    assert result.final_decision.value == "PASS_WARNING"


def test_v11_strategy_fail_before_rescoring():
    """Strategy FAIL (SQ_NO_FIRED) → short-circuits before rescoring check"""
    cfg = _v11_config()
    engine = make_filter_engine(cfg)
    result = engine.run(_v11_signal(squeeze_fired=0))
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "SQ_NO_FIRED" in fail_codes
    # BACKEND_SCORE_THRESHOLD should NOT be in results (short-circuited)
    rule_codes = [r.rule_code for r in result.filter_results]
    assert "BACKEND_SCORE_THRESHOLD" not in rule_codes


def test_duplicate_check_uses_repository_entry_range_lookup():
    engine = make_filter_engine()
    engine.signal_repo.find_recent_similar_by_entry_range.return_value = [MagicMock()]
    engine.signal_repo.find_recent_similar.return_value = []

    result = engine.run(make_signal())

    assert result.final_decision == "REJECT"
    engine.signal_repo.find_recent_similar_by_entry_range.assert_called_once_with(
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        signal_type="LONG_V73",
        entry_price=68250.5,
        tolerance_pct=0.002,
        since_minutes=10,
        exclude_signal_id="test-001",
    )
    engine.signal_repo.find_recent_similar.assert_not_called()
