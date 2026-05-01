from __future__ import annotations

from collections import defaultdict


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
    for row in rows:
        key = (row.get("timeframe"), row.get("signal_type"))
        buckets[key].append(row)

    bucket_reports = []
    insufficient = 0
    eligible = 0
    for (timeframe, signal_type), items in buckets.items():
        samples = len(items)
        avg_r = sum(float(item.get("r_multiple") or 0) for item in items) / samples if samples else 0.0
        wins = sum(1 for item in items if item.get("is_win") is True)
        if samples < min_samples:
            recommendation = "INSUFFICIENT_DATA"
            insufficient += 1
        elif avg_r < 0:
            recommendation = "REVIEW_TIGHTEN"
            eligible += 1
        else:
            recommendation = "KEEP"
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

    return {
        "sample_health": {
            "closed_outcomes": closed_outcomes,
            "min_samples": min_samples,
            "eligible_buckets": eligible,
            "insufficient_buckets": insufficient,
        },
        "bucket_performance": bucket_reports,
        "threshold_suggestions": [],
    }
