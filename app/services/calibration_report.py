from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


_ALLOWED_RECOMMENDATIONS = {
    "KEEP",
    "WATCH",
    "REVIEW_TIGHTEN",
    "REVIEW_RELAX",
    "INSUFFICIENT_DATA",
}


def build_calibration_report(rows: list[dict], min_samples: int) -> dict:
    closed_outcomes = len(rows)
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    rules: dict[tuple, list[dict]] = defaultdict(list)
    confidence_by_timeframe: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        key = (row.get("timeframe"), row.get("signal_type"))
        buckets[key].append(row)
        if row.get("indicator_confidence") is not None:
            confidence_by_timeframe[str(row.get("timeframe"))].append(row)
        for filter_result in row.get("filter_results") or []:
            rule_key = (
                filter_result.get("rule_code"),
                filter_result.get("result"),
                filter_result.get("severity"),
            )
            rules[rule_key].append(row)

    bucket_reports = []
    insufficient = 0
    eligible = 0
    for (timeframe, signal_type), items in buckets.items():
        samples = len(items)
        avg_r = _avg_r(items)
        wins = sum(1 for item in items if item.get("is_win") is True)
        recommendation = _recommend(samples, avg_r, min_samples)
        if recommendation == "INSUFFICIENT_DATA":
            insufficient += 1
        else:
            eligible += 1
        bucket_reports.append(
            {
                "bucket": {"timeframe": timeframe, "signal_type": signal_type},
                "samples": samples,
                "win_rate": round((wins / samples), 4) if samples else 0.0,
                "avg_r": round(avg_r, 4),
                "recommendation": recommendation,
            }
        )

    rule_impact = []
    for (rule_code, result, severity), items in rules.items():
        samples = len(items)
        avg_r = _avg_r(items)
        wins = sum(1 for item in items if item.get("is_win") is True)
        rule_impact.append(
            {
                "rule_code": rule_code,
                "result": result,
                "severity": severity,
                "samples": samples,
                "win_rate": round((wins / samples), 4) if samples else 0.0,
                "avg_r": round(avg_r, 4),
                "recommendation": _recommend(samples, avg_r, min_samples),
            }
        )
    rule_impact.sort(key=lambda item: (str(item["rule_code"]), str(item["result"])))

    threshold_suggestions = _build_threshold_suggestions(confidence_by_timeframe, min_samples)

    return {
        "sample_health": {
            "closed_outcomes": closed_outcomes,
            "min_samples": min_samples,
            "eligible_buckets": eligible,
            "insufficient_buckets": insufficient,
        },
        "bucket_performance": bucket_reports,
        "rule_impact": rule_impact,
        "threshold_suggestions": threshold_suggestions,
    }


def _avg_r(items: list[dict]) -> float:
    if not items:
        return 0.0
    return sum(float(item.get("r_multiple") or 0) for item in items) / len(items)


def _recommend(samples: int, avg_r: float, min_samples: int) -> str:
    if samples < min_samples:
        return "INSUFFICIENT_DATA"
    if avg_r < 0:
        return "REVIEW_TIGHTEN"
    if avg_r < 0.1:
        return "WATCH"
    return "KEEP"


def _build_threshold_suggestions(rows_by_timeframe: dict[str, list[dict]], min_samples: int) -> list[dict[str, Any]]:
    suggestions = []
    for timeframe, rows in rows_by_timeframe.items():
        low_confidence_rows = [
            row for row in rows
            if row.get("indicator_confidence") is not None and float(row["indicator_confidence"]) < 0.8
        ]
        if len(low_confidence_rows) < min_samples:
            continue
        avg_r = _avg_r(low_confidence_rows)
        if avg_r >= 0:
            continue
        confidence_values = [float(row["indicator_confidence"]) for row in low_confidence_rows]
        suggested = max(0.0, min(1.0, round(max(confidence_values) + 0.01, 2)))
        suggestions.append(
            {
                "config_key": f"confidence_thresholds.{timeframe}",
                "current": None,
                "suggested": suggested,
                "reason": (
                    f"Signals below {suggested:.2f} show negative avg R "
                    f"over {len(low_confidence_rows)} closed outcomes"
                ),
                "confidence": "LOW" if len(low_confidence_rows) < (min_samples * 2) else "MEDIUM",
                "samples": len(low_confidence_rows),
                "avg_r": round(mean(float(row.get("r_multiple") or 0) for row in low_confidence_rows), 4),
            }
        )
    return suggestions
