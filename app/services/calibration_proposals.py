from __future__ import annotations

from datetime import datetime, timezone


def build_calibration_proposals(
    report: dict,
    current_config: dict,
    current_config_version: int,
    min_samples: int,
) -> dict:
    proposals = []
    for item in report.get("threshold_suggestions", []):
        config_key = str(item["config_key"])
        parts = config_key.split(".")
        if len(parts) != 2 or parts[0] != "confidence_thresholds":
            continue
        timeframe = parts[1]
        samples = int(item.get("samples") or 0)
        if samples < min_samples:
            continue
        current_value = current_config.get("confidence_thresholds", {}).get(timeframe)
        if current_value is None:
            continue
        current = float(current_value)
        raw_suggested = float(item["suggested"])
        max_step = 0.03
        if raw_suggested > current:
            suggested = min(raw_suggested, current + max_step)
            direction = "TIGHTEN"
        elif raw_suggested < current:
            suggested = max(raw_suggested, current - max_step)
            direction = "RELAX"
        else:
            continue
        suggested = round(max(0.0, min(1.0, suggested)), 2)
        proposals.append(
            {
                "id": f"confidence_thresholds.{timeframe}.{direction.lower()}.{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "config_path": config_key,
                "current": current,
                "suggested": suggested,
                "direction": direction,
                "reason": item.get("reason") or "Calibration report suggested a threshold change",
                "sample_health": {
                    "samples": samples,
                    "win_rate": item.get("win_rate", 0.0),
                    "avg_r": item.get("avg_r", 0.0),
                },
                "confidence": "LOW" if samples < min_samples * 2 else item.get("confidence", "MEDIUM"),
                "risk": f"May change signal volume on {timeframe}",
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_config_version": current_config_version,
        "proposals": proposals,
    }
