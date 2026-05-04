from __future__ import annotations

from app.services.calibration_report import build_calibration_report


def test_calibration_report_marks_insufficient_data():
    report = build_calibration_report(
        [{"timeframe": "5m", "signal_type": "LONG_V73", "r_multiple": 1.0, "is_win": True}],
        min_samples=2,
    )
    assert report["sample_health"]["insufficient_buckets"] == 1
    assert report["bucket_performance"][0]["recommendation"] == "INSUFFICIENT_DATA"


def test_calibration_report_marks_negative_avg_r_for_review():
    report = build_calibration_report(
        [
            {"timeframe": "5m", "signal_type": "LONG_V73", "r_multiple": -1.0, "is_win": False},
            {"timeframe": "5m", "signal_type": "LONG_V73", "r_multiple": -0.5, "is_win": False},
        ],
        min_samples=2,
    )
    assert report["bucket_performance"][0]["recommendation"] == "REVIEW_TIGHTEN"

def test_calibration_report_includes_rule_impact_with_sample_guard():
    report = build_calibration_report(
        [
            {
                "timeframe": "5m",
                "signal_type": "LONG_V73",
                "r_multiple": -1.0,
                "is_win": False,
                "filter_results": [
                    {"rule_code": "LOW_VOLUME_WARNING", "result": "WARN", "severity": "MEDIUM"}
                ],
            },
            {
                "timeframe": "5m",
                "signal_type": "LONG_V73",
                "r_multiple": -0.5,
                "is_win": False,
                "filter_results": [
                    {"rule_code": "LOW_VOLUME_WARNING", "result": "WARN", "severity": "MEDIUM"}
                ],
            },
        ],
        min_samples=2,
    )

    assert report["rule_impact"][0]["rule_code"] == "LOW_VOLUME_WARNING"
    assert report["rule_impact"][0]["recommendation"] == "REVIEW_TIGHTEN"

def test_calibration_report_suggests_confidence_threshold_only_with_enough_samples():
    report = build_calibration_report(
        [
            {"timeframe": "5m", "signal_type": "LONG_V73", "r_multiple": -0.5, "is_win": False, "indicator_confidence": 0.76},
            {"timeframe": "5m", "signal_type": "LONG_V73", "r_multiple": -0.2, "is_win": False, "indicator_confidence": 0.79},
            {"timeframe": "5m", "signal_type": "LONG_V73", "r_multiple": 1.0, "is_win": True, "indicator_confidence": 0.86},
        ],
        min_samples=2,
    )

    assert report["threshold_suggestions"]
    assert report["threshold_suggestions"][0]["config_key"] == "confidence_thresholds.5m"


def test_rows_to_calibration_payload_transforms_outcome_rows():
    from app.services.calibration_report import rows_to_calibration_payload
    from collections import namedtuple

    Row = namedtuple("Row", ["id", "timeframe", "signal_type", "r_multiple", "is_win", "indicator_confidence"])
    outcome_rows = [
        Row(id="sig1", timeframe="5m", signal_type="LONG_V73", r_multiple=1.5, is_win=True, indicator_confidence=0.85),
        Row(id="sig2", timeframe="15m", signal_type="SHORT_V73", r_multiple=-0.5, is_win=False, indicator_confidence=0.72),
    ]
    filter_rows_by_signal = {
        "sig1": [{"rule_code": "SYMBOL_ALLOWED", "result": "PASS", "severity": "INFO"}],
        "sig2": [{"rule_code": "LOW_VOLUME_WARNING", "result": "WARN", "severity": "MEDIUM"}],
    }

    payload = rows_to_calibration_payload(outcome_rows, filter_rows_by_signal)

    assert len(payload) == 2
    assert payload[0]["timeframe"] == "5m"
    assert payload[0]["signal_type"] == "LONG_V73"
    assert payload[0]["r_multiple"] == 1.5
    assert payload[0]["is_win"] is True
    assert payload[0]["indicator_confidence"] == 0.85
    assert payload[0]["filter_results"] == [{"rule_code": "SYMBOL_ALLOWED", "result": "PASS", "severity": "INFO"}]
    assert payload[1]["timeframe"] == "15m"
    assert payload[1]["filter_results"] == [{"rule_code": "LOW_VOLUME_WARNING", "result": "WARN", "severity": "MEDIUM"}]
