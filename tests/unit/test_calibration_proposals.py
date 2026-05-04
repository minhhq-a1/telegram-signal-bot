from __future__ import annotations

from app.services.calibration_proposals import build_calibration_proposals


def test_confidence_threshold_proposal_clamps_step() -> None:
    report = {
        "threshold_suggestions": [
            {
                "config_key": "confidence_thresholds.5m",
                "suggested": 0.9,
                "samples": 80,
                "avg_r": -0.2,
                "confidence": "MEDIUM",
                "reason": "negative avg R",
            }
        ]
    }
    config = {"confidence_thresholds": {"5m": 0.78}}

    proposals = build_calibration_proposals(report, config, current_config_version=3, min_samples=30)

    assert proposals["current_config_version"] == 3
    assert proposals["proposals"][0]["current"] == 0.78
    assert proposals["proposals"][0]["suggested"] == 0.81
    assert proposals["proposals"][0]["direction"] == "TIGHTEN"


def test_no_proposal_when_samples_below_minimum() -> None:
    report = {
        "threshold_suggestions": [
            {"config_key": "confidence_thresholds.5m", "suggested": 0.81, "samples": 10, "avg_r": -0.2, "confidence": "LOW", "reason": "negative avg R"}
        ]
    }
    config = {"confidence_thresholds": {"5m": 0.78}}

    proposals = build_calibration_proposals(report, config, current_config_version=3, min_samples=30)

    assert proposals["proposals"] == []
