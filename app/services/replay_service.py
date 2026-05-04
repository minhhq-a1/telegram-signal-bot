from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.schemas import TradingViewWebhookPayload
from app.services.filter_engine import FilterEngine
from app.services.signal_normalizer import SignalNormalizer


class _NoopSignalRepo:
    def find_recent_similar_by_entry_range(self, **kwargs):
        return []

    def find_recent_pass_main_same_side(self, **kwargs):
        return []


class _NoopMarketRepo:
    def find_active_around(self, *args, **kwargs):
        return []


class ReplayService:
    def __init__(self, config: dict):
        self.config = config

    def replay_payload(self, payload_dict: dict[str, Any], file_label: str) -> dict[str, Any]:
        try:
            payload = TradingViewWebhookPayload.model_validate(payload_dict)
            norm = SignalNormalizer.normalize("replay", payload)
            result = FilterEngine(self.config, _NoopSignalRepo(), _NoopMarketRepo()).run(norm)
            return {
                "file": file_label,
                "status": "ok",
                "signal_id": norm["signal_id"],
                "decision": result.final_decision.value,
                "route": result.route.value,
                "server_score": result.server_score,
                "decision_reason": result.decision_reason,
                "rule_codes": [item.rule_code for item in result.filter_results],
            }
        except Exception as exc:
            return {"file": file_label, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    def compare_payload(self, payload_dict: dict[str, Any], proposed_config: dict, file_label: str) -> dict[str, Any]:
        current = self.replay_payload(payload_dict, file_label)
        proposed = ReplayService(proposed_config).replay_payload(payload_dict, file_label)
        if current["status"] != "ok" or proposed["status"] != "ok":
            return {"file": file_label, "status": "error", "current": current, "proposed": proposed}
        current_rules = set(current.get("rule_codes", []))
        proposed_rules = set(proposed.get("rule_codes", []))
        return {
            "file": file_label,
            "status": "ok",
            "signal_id": current["signal_id"],
            "current_decision": current["decision"],
            "proposed_decision": proposed["decision"],
            "current_route": current["route"],
            "proposed_route": proposed["route"],
            "current_server_score": current["server_score"],
            "proposed_server_score": proposed["server_score"],
            "decision_changed": current["decision"] != proposed["decision"],
            "changed_rule_codes": sorted(current_rules.symmetric_difference(proposed_rules)),
        }


def load_json_payloads(input_path: Path) -> list[tuple[Path, dict[str, Any]]]:
    paths = [input_path] if input_path.is_file() else sorted(path for path in input_path.rglob("*.json") if path.is_file())
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
