import pytest

from app.services.reject_codes import RejectCode, rule_code_to_reject_code


class TestRejectCodeEnum:
    def test_all_v10_reject_codes_exist(self):
        assert RejectCode.INVALID_SYMBOL
        assert RejectCode.UNSUPPORTED_TIMEFRAME
        assert RejectCode.INVALID_PRICE_STRUCTURE
        assert RejectCode.INVALID_NUMERIC_RANGE
        assert RejectCode.INVALID_RR_PROFILE
        assert RejectCode.LOW_CONFIDENCE
        assert RejectCode.DUPLICATE_SIGNAL
        assert RejectCode.NEWS_BLOCKED
        assert RejectCode.COUNTER_TREND_HARD

    def test_v11_strategy_reject_codes_exist(self):
        assert RejectCode.SQ_NO_FIRED
        assert RejectCode.SQ_BAD_MOM_DIRECTION
        assert RejectCode.SQ_BAD_VOL_REGIME
        assert RejectCode.SQ_BAD_STRATEGY_NAME
        assert RejectCode.SQ_RSI_TOO_LOW
        assert RejectCode.SQ_KC_POSITION_TOO_HIGH
        assert RejectCode.S_BASE_BAD_STRATEGY_NAME
        assert RejectCode.S_BASE_RSI_TOO_LOW
        assert RejectCode.S_BASE_STOCH_TOO_LOW
        assert RejectCode.L_BASE_BAD_STRATEGY_NAME
        assert RejectCode.L_BASE_RSI_TOO_HIGH
        assert RejectCode.L_BASE_STOCH_TOO_HIGH
        assert RejectCode.RR_PROFILE_MISMATCH
        assert RejectCode.BACKEND_SCORE_TOO_LOW
        assert RejectCode.UNKNOWN


class TestRuleCodeToRejectCode:
    def test_v10_hard_validation_rules(self):
        assert rule_code_to_reject_code("SYMBOL_ALLOWED") == RejectCode.INVALID_SYMBOL
        assert rule_code_to_reject_code("TIMEFRAME_ALLOWED") == RejectCode.UNSUPPORTED_TIMEFRAME
        assert rule_code_to_reject_code("PRICE_VALID") == RejectCode.INVALID_NUMERIC_RANGE
        assert rule_code_to_reject_code("DIRECTION_SANITY_VALID") == RejectCode.INVALID_PRICE_STRUCTURE
        assert rule_code_to_reject_code("MIN_RR_REQUIRED") == RejectCode.INVALID_RR_PROFILE
        assert rule_code_to_reject_code("CONFIDENCE_RANGE_VALID") == RejectCode.LOW_CONFIDENCE
        assert rule_code_to_reject_code("MIN_CONFIDENCE_BY_TF") == RejectCode.LOW_CONFIDENCE

    def test_v10_business_rules(self):
        assert rule_code_to_reject_code("DUPLICATE_SUPPRESSION") == RejectCode.DUPLICATE_SIGNAL
        assert rule_code_to_reject_code("NEWS_BLOCK") == RejectCode.NEWS_BLOCKED
        assert rule_code_to_reject_code("REGIME_HARD_BLOCK") == RejectCode.COUNTER_TREND_HARD

    def test_v11_short_squeeze_hard_rules(self):
        assert rule_code_to_reject_code("SQ_NO_FIRED") == RejectCode.SQ_NO_FIRED
        assert rule_code_to_reject_code("SQ_BAD_MOM_DIRECTION") == RejectCode.SQ_BAD_MOM_DIRECTION
        assert rule_code_to_reject_code("SQ_BAD_VOL_REGIME") == RejectCode.SQ_BAD_VOL_REGIME
        assert rule_code_to_reject_code("SQ_BAD_STRATEGY_NAME") == RejectCode.SQ_BAD_STRATEGY_NAME

    def test_v11_short_squeeze_quality_floors(self):
        assert rule_code_to_reject_code("SQ_RSI_FLOOR") == RejectCode.SQ_RSI_TOO_LOW
        assert rule_code_to_reject_code("SQ_KC_POSITION_FLOOR") == RejectCode.SQ_KC_POSITION_TOO_HIGH

    def test_v11_short_v73_rules(self):
        assert rule_code_to_reject_code("S_BASE_BAD_STRATEGY_NAME") == RejectCode.S_BASE_BAD_STRATEGY_NAME
        assert rule_code_to_reject_code("S_BASE_RSI_FLOOR") == RejectCode.S_BASE_RSI_TOO_LOW
        assert rule_code_to_reject_code("S_BASE_STOCH_FLOOR") == RejectCode.S_BASE_STOCH_TOO_LOW

    def test_v11_long_v73_rules(self):
        assert rule_code_to_reject_code("L_BASE_BAD_STRATEGY_NAME") == RejectCode.L_BASE_BAD_STRATEGY_NAME
        assert rule_code_to_reject_code("L_BASE_RSI_FLOOR") == RejectCode.L_BASE_RSI_TOO_HIGH
        assert rule_code_to_reject_code("L_BASE_STOCH_FLOOR") == RejectCode.L_BASE_STOCH_TOO_HIGH

    def test_v11_new_rules(self):
        assert rule_code_to_reject_code("RR_PROFILE_MATCH") == RejectCode.RR_PROFILE_MISMATCH
        assert rule_code_to_reject_code("BACKEND_SCORE_THRESHOLD") == RejectCode.BACKEND_SCORE_TOO_LOW

    def test_unknown_rule_returns_unknown(self):
        assert rule_code_to_reject_code("SOMETHING_NEW") == RejectCode.UNKNOWN
        assert rule_code_to_reject_code("") == RejectCode.UNKNOWN
        assert rule_code_to_reject_code("CUSTOM_RULE_X") == RejectCode.UNKNOWN
