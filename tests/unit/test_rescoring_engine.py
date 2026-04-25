import pytest

from app.services.rescoring_engine import rescore


def _cfg():
    return {
        "rescoring": {
            "SHORT_SQUEEZE": {
                "base": 70,
                "bonuses": {
                    "vol_regime_breakout_imminent": 8,
                    "regime_weak_trend_down": 6,
                    "regime_strong_trend_down": 8,
                    "mom_direction_neg1": 5,
                    "squeeze_bars_ge_4": 3,
                    "squeeze_bars_ge_6": 5,
                    "rsi_ge_40": 4,
                    "rsi_slope_le_neg4": 4,
                    "atr_percentile_ge_70": 3,
                    "kc_position_le_040": 3,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "regime_weak_trend_up": -8,
                    "rsi_lt_35": -8,
                    "atr_pct_lt_020": -8,
                    "atr_pct_gt_150": -5,
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
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "vol_ranging_high": -6,
                    "atr_pct_lt_020": -6,
                },
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
                "penalties": {
                    "regime_strong_trend_down": -15,
                    "vol_ranging_high": -6,
                    "atr_pct_lt_020": -6,
                },
            },
        }
    }


class TestShortSqueezeRescoring:
    def test_ideal_signal_scores_100(self):
        # All positive signals → score capped at 100
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": 0.91,
            "regime": "STRONG_TREND_DOWN",
            "vol_regime": "BREAKOUT_IMMINENT",
            "mom_direction": -1,
            "squeeze_bars": 6,
            "rsi": 37.5,
            "rsi_slope": -5.7,
            "atr_percentile": 78,
            "kc_position": 0.31,
            "atr_pct": 0.49,
        }
        score, items = rescore(signal, _cfg())
        assert score == 100
        assert any("vol_regime_breakout_imminent" in it for it in items)

    def test_all_bonuses_applied(self):
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": 0.91,  # >= 0.90
            "regime": "STRONG_TREND_DOWN",  # regime_strong_trend_down + regime_trend_down
            "vol_regime": "BREAKOUT_IMMINENT",  # vol_regime_breakout_imminent
            "mom_direction": -1,  # mom_direction_neg1
            "squeeze_bars": 6,  # squeeze_bars_ge_4 + squeeze_bars_ge_6
            "rsi": 40.1,  # rsi_ge_40
            "rsi_slope": -5.7,  # rsi_slope_le_neg4
            "atr_percentile": 78,  # atr_percentile_ge_70
            "kc_position": 0.31,  # kc_position_le_040
            "atr_pct": 0.49,  # no penalty
        }
        score, items = rescore(signal, _cfg())
        # 70 + 8 + 8 + 6 + 5 + 3 + 5 + 4 + 4 + 3 + 3 + 3 = 122 → clamp 100
        assert score == 100
        assert any("vol_regime_breakout_imminent" in it for it in items)
        assert any("mom_direction_neg1" in it for it in items)
        assert any("squeeze_bars_ge_6" in it for it in items)

    def test_penalty_applied(self):
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": 0.80,
            "regime": "STRONG_TREND_UP",
            "mom_direction": 1,
            "rsi": 30,
            "atr_pct": 0.10,
        }
        score, items = rescore(signal, _cfg())
        # 70 - 15 (strong_up) - 8 (rsi<35) - 8 (atr<0.20) = 39
        assert score == 39
        assert any("regime_strong_trend_up" in it for it in items)

    def test_weak_trend_down_bonus(self):
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": 0.50,
            "regime": "WEAK_TREND_DOWN",
        }
        score, items = rescore(signal, _cfg())
        # 70 + 6 (weak_trend_down) = 76 (regime_trend_down NOT in SHORT_SQUEEZE config)
        assert score == 76
        assert any("regime_weak_trend_down" in it for it in items)


class TestShortV73Rescoring:
    def test_base_plus_bonus(self):
        signal = {
            "signal_type": "SHORT_V73",
            "indicator_confidence": 0.91,
            "rsi": 72,
            "stoch_k": 88,
            "regime": "WEAK_TREND_DOWN",
        }
        score, items = rescore(signal, _cfg())
        # 72 + 5 (rsi>=70) + 5 (stoch>=85) + 3 (conf>=0.90) + 6 (trend_down) = 91
        assert score == 91


class TestLongV73Rescoring:
    def test_base_plus_bonus(self):
        signal = {
            "signal_type": "LONG_V73",
            "indicator_confidence": 0.92,
            "rsi": 24,
            "stoch_k": 8,
            "regime": "WEAK_TREND_UP",
        }
        score, items = rescore(signal, _cfg())
        # 72 + 5 (rsi<=25) + 5 (stoch<=10) + 3 (conf>=0.90) + 6 (trend_up) = 91
        assert score == 91


class TestRescoringEdgeCases:
    def test_unknown_signal_type_falls_back_to_70(self):
        signal = {"signal_type": "UNKNOWN_X"}
        score, items = rescore(signal, _cfg())
        assert score == 70
        assert "base_fallback=70" in items

    def test_score_clamped_to_0(self):
        # All penalties, no bonuses → should not go below 0
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": 0.0,
            "regime": "STRONG_TREND_UP",
            "mom_direction": 1,
            "rsi": 10,
            "atr_pct": 0.05,
            "vol_regime": "RANGING_HIGH_VOL",
        }
        score, _ = rescore(signal, _cfg())
        assert 0 <= score <= 100

    def test_score_exactly_at_boundaries(self):
        # Boundary test: rsi=40 (>=40), mom_direction=-1, regime=WEAK_TREND_DOWN
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": 0.50,
            "rsi": 40,
            "mom_direction": -1,
            "regime": "WEAK_TREND_DOWN",
        }
        score, items = rescore(signal, _cfg())
        # 70 + 6 (weak_trend_down) + 5 (mom=-1) + 4 (rsi>=40) = 85
        assert score == 85
        assert any("regime_weak_trend_down" in it for it in items)
        assert any("mom_direction_neg1" in it for it in items)
        assert any("rsi_ge_40" in it for it in items)

    def test_none_values_handled(self):
        signal = {
            "signal_type": "SHORT_SQUEEZE",
            "indicator_confidence": None,
            "regime": None,
            "vol_regime": None,
            "rsi": None,
            "rsi_slope": None,
            "stoch_k": None,
        }
        score, items = rescore(signal, _cfg())
        # Only base = 70
        assert score == 70
        assert "base=70" in items

    def test_int_float_compatibility(self):
        # Pine sometimes sends int where float is expected
        signal = {
            "signal_type": "SHORT_V73",
            "indicator_confidence": 1,  # int instead of float
            "rsi": 70,  # int
            "stoch_k": 85,  # int
        }
        score, _ = rescore(signal, _cfg())
        # 72 + 5 (rsi>=70) + 5 (stoch>=85) + 3 (conf>=0.90) = 85
        assert score == 85
