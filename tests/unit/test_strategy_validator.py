import pytest

from app.services.strategy_validator import validate_strategy
from app.core.enums import RuleResult, RuleSeverity


def _cfg():
    return {
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {
                "rsi_min": 35,
                "rsi_slope_max": -2,
                "kc_position_max": 0.55,
                "atr_pct_min": 0.20,
            },
            "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
            "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
        }
    }


def _sq(**overrides):
    base = {
        "side": "SHORT",
        "signal_type": "SHORT_SQUEEZE",
        "strategy": "KELTNER_SQUEEZE",
        "squeeze_fired": 1,
        "mom_direction": -1,
        "vol_regime": "BREAKOUT_IMMINENT",
        "rsi": 37.5,
        "rsi_slope": -5.7,
        "kc_position": 0.31,
        "atr_pct": 0.49,
    }
    base.update(overrides)
    return base


class TestShortSqueezeValidator:
    def test_pass_all_rules(self):
        results = validate_strategy(_sq(), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_NO_FIRED"].result == RuleResult.PASS
        assert codes["SQ_BAD_MOM_DIRECTION"].result == RuleResult.PASS
        assert codes["SQ_BAD_VOL_REGIME"].result == RuleResult.PASS
        assert codes["SQ_BAD_STRATEGY_NAME"].result == RuleResult.PASS
        assert codes["SQ_RSI_FLOOR"].result == RuleResult.PASS
        assert codes["SQ_KC_POSITION_FLOOR"].result == RuleResult.PASS

    def test_fail_not_fired_int(self):
        results = validate_strategy(_sq(squeeze_fired=0), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_NO_FIRED"].result == RuleResult.FAIL
        assert codes["SQ_NO_FIRED"].severity == RuleSeverity.HIGH

    def test_fail_not_fired_bool(self):
        results = validate_strategy(_sq(squeeze_fired=False), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_NO_FIRED"].result == RuleResult.FAIL

    def test_fail_mom_direction_positive(self):
        results = validate_strategy(_sq(mom_direction=1), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_BAD_MOM_DIRECTION"].result == RuleResult.FAIL
        assert codes["SQ_BAD_MOM_DIRECTION"].severity == RuleSeverity.HIGH

    def test_fail_mom_direction_zero(self):
        results = validate_strategy(_sq(mom_direction=0), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_BAD_MOM_DIRECTION"].result == RuleResult.FAIL

    def test_fail_bad_vol_regime(self):
        for bad in ["TRENDING_LOW_VOL", "RANGING_HIGH_VOL", "SQUEEZE_BUILDING", "UNKNOWN_REGIME"]:
            results = validate_strategy(_sq(vol_regime=bad), _cfg())
            codes = {r.rule_code: r for r in results}
            assert codes["SQ_BAD_VOL_REGIME"].result == RuleResult.FAIL, f"vol_regime={bad} should FAIL"

    def test_pass_vol_regime(self):
        # Only BREAKOUT_IMMINENT passes
        results = validate_strategy(_sq(vol_regime="BREAKOUT_IMMINENT"), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_BAD_VOL_REGIME"].result == RuleResult.PASS

    def test_fail_bad_strategy_name(self):
        results = validate_strategy(_sq(strategy="RSI_STOCH_V73"), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_BAD_STRATEGY_NAME"].result == RuleResult.FAIL

    def test_warn_rsi_below_min(self):
        results = validate_strategy(_sq(rsi=30), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_RSI_FLOOR"].result == RuleResult.WARN
        assert codes["SQ_RSI_FLOOR"].severity == RuleSeverity.MEDIUM

    def test_pass_rsi_at_min(self):
        results = validate_strategy(_sq(rsi=35), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_RSI_FLOOR"].result == RuleResult.PASS

    def test_warn_kc_above_max(self):
        results = validate_strategy(_sq(kc_position=0.80), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_KC_POSITION_FLOOR"].result == RuleResult.WARN
        assert codes["SQ_KC_POSITION_FLOOR"].severity == RuleSeverity.MEDIUM

    def test_pass_kc_at_max(self):
        results = validate_strategy(_sq(kc_position=0.55), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_KC_POSITION_FLOOR"].result == RuleResult.PASS

    def test_missing_optional_fields_pass(self):
        # Fields like rsi, kc_position, rsi_slope are optional
        results = validate_strategy(_sq(rsi=None, kc_position=None), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_RSI_FLOOR"].result == RuleResult.PASS
        assert codes["SQ_KC_POSITION_FLOOR"].result == RuleResult.PASS

    def test_unknown_signal_type_returns_empty(self):
        assert validate_strategy({"signal_type": "UNKNOWN_X"}, _cfg()) == []


def _sv73(**overrides):
    base = {
        "side": "SHORT",
        "signal_type": "SHORT_V73",
        "strategy": "RSI_STOCH_V73",
        "rsi": 72,
        "stoch_k": 80,
    }
    base.update(overrides)
    return base


class TestShortV73Validator:
    def test_pass_all_rules(self):
        results = validate_strategy(_sv73(), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["S_BASE_BAD_STRATEGY_NAME"].result == RuleResult.PASS
        assert codes["S_BASE_RSI_FLOOR"].result == RuleResult.PASS
        assert codes["S_BASE_STOCH_FLOOR"].result == RuleResult.PASS

    def test_fail_strategy_name(self):
        results = validate_strategy(_sv73(strategy="KELTNER_SQUEEZE"), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["S_BASE_BAD_STRATEGY_NAME"].result == RuleResult.FAIL

    def test_warn_rsi_below_min(self):
        results = validate_strategy(_sv73(rsi=55), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["S_BASE_RSI_FLOOR"].result == RuleResult.WARN

    def test_warn_stoch_below_min(self):
        results = validate_strategy(_sv73(stoch_k=61), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["S_BASE_STOCH_FLOOR"].result == RuleResult.WARN

    def test_pass_at_thresholds(self):
        results = validate_strategy(_sv73(rsi=60, stoch_k=70), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["S_BASE_RSI_FLOOR"].result == RuleResult.PASS
        assert codes["S_BASE_STOCH_FLOOR"].result == RuleResult.PASS


def _lv73(**overrides):
    base = {
        "side": "LONG",
        "signal_type": "LONG_V73",
        "strategy": "RSI_STOCH_V73",
        "rsi": 28,
        "stoch_k": 15,
    }
    base.update(overrides)
    return base


class TestLongV73Validator:
    def test_pass_all_rules(self):
        results = validate_strategy(_lv73(), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["L_BASE_BAD_STRATEGY_NAME"].result == RuleResult.PASS
        assert codes["L_BASE_RSI_FLOOR"].result == RuleResult.PASS
        assert codes["L_BASE_STOCH_FLOOR"].result == RuleResult.PASS

    def test_fail_strategy_name(self):
        results = validate_strategy(_lv73(strategy="KELTNER_SQUEEZE"), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["L_BASE_BAD_STRATEGY_NAME"].result == RuleResult.FAIL

    def test_warn_rsi_above_max(self):
        results = validate_strategy(_lv73(rsi=41), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["L_BASE_RSI_FLOOR"].result == RuleResult.WARN

    def test_warn_stoch_above_max(self):
        results = validate_strategy(_lv73(stoch_k=25), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["L_BASE_STOCH_FLOOR"].result == RuleResult.WARN

    def test_pass_at_thresholds(self):
        results = validate_strategy(_lv73(rsi=35, stoch_k=20), _cfg())
        codes = {r.rule_code: r for r in results}
        assert codes["L_BASE_RSI_FLOOR"].result == RuleResult.PASS
        assert codes["L_BASE_STOCH_FLOOR"].result == RuleResult.PASS
