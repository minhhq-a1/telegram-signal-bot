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
