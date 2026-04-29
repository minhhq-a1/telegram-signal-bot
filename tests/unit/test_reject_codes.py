import pytest

from app.services.reject_codes import RejectCode, rule_code_to_reject_code


def test_known_rule_codes_have_reject_codes():
    assert rule_code_to_reject_code("SYMBOL_ALLOWED") == RejectCode.INVALID_SYMBOL
    assert rule_code_to_reject_code("TIMEFRAME_ALLOWED") == RejectCode.UNSUPPORTED_TIMEFRAME
    assert rule_code_to_reject_code("DIRECTION_SANITY_VALID") == RejectCode.INVALID_PRICE_STRUCTURE
    assert rule_code_to_reject_code("MIN_RR_REQUIRED") == RejectCode.INVALID_RR_PROFILE
    assert rule_code_to_reject_code("MIN_CONFIDENCE_BY_TF") == RejectCode.LOW_CONFIDENCE
    assert rule_code_to_reject_code("DUPLICATE_SUPPRESSION") == RejectCode.DUPLICATE_SIGNAL
    assert rule_code_to_reject_code("NEWS_BLOCK") == RejectCode.NEWS_BLOCKED
    assert rule_code_to_reject_code("REGIME_HARD_BLOCK") == RejectCode.COUNTER_TREND_HARD
    assert rule_code_to_reject_code("SQ_NO_FIRED") == RejectCode.SQ_NO_FIRED
    assert rule_code_to_reject_code("SQ_BAD_MOM_DIRECTION") == RejectCode.SQ_BAD_MOM_DIRECTION
    assert rule_code_to_reject_code("SQ_BAD_VOL_REGIME") == RejectCode.SQ_BAD_VOL_REGIME
    assert rule_code_to_reject_code("SQ_BAD_STRATEGY_NAME") == RejectCode.SQ_BAD_STRATEGY_NAME
    assert rule_code_to_reject_code("S_BASE_BAD_STRATEGY_NAME") == RejectCode.S_BASE_BAD_STRATEGY_NAME
    assert rule_code_to_reject_code("L_BASE_BAD_STRATEGY_NAME") == RejectCode.L_BASE_BAD_STRATEGY_NAME
    assert rule_code_to_reject_code("RR_PROFILE_MATCH") == RejectCode.RR_PROFILE_MISMATCH
    assert rule_code_to_reject_code("BACKEND_SCORE_THRESHOLD") == RejectCode.BACKEND_SCORE_TOO_LOW


def test_unknown_rule_code_returns_generic():
    assert rule_code_to_reject_code("SOMETHING_NEW") == RejectCode.UNKNOWN


def test_reject_code_is_str_enum():
    """RejectCode is a str,Enum mixin — members serialize as plain strings in JSON."""
    assert RejectCode.SQ_NO_FIRED == "SQ_NO_FIRED"
    assert isinstance(RejectCode.SQ_NO_FIRED, str)
