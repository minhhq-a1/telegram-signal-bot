from unittest.mock import MagicMock
from app.services.filter_engine import FilterEngine

def make_filter_engine(config_overrides=None):
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m","3m","5m","12m","15m"],
        "confidence_thresholds": {"5m": 0.78},
        "cooldown_minutes": {"5m": 10},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
        "enable_news_block": True,
        "news_block_before_min": 15,
        "news_block_after_min": 30,
        # Không có main_score_threshold/warning_score_threshold
        # Boolean gate không cần score threshold
    }
    if config_overrides:
        config.update(config_overrides)

    mock_signal_repo = MagicMock()
    mock_signal_repo.find_recent_pass_main_same_side.return_value = []
    mock_signal_repo.find_recent_similar.return_value = []

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

# Test 3: STRONG_TREND_DOWN + LONG → FAIL → REJECT
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
    engine.signal_repo.find_recent_similar.return_value = [near_match]

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
    engine.signal_repo.find_recent_similar.return_value = [far_enough]

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
