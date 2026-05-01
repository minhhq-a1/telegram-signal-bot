#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.signal_normalizer import SignalNormalizer
from app.services.filter_engine import FilterEngine
from app.domain.schemas import TradingViewWebhookPayload
from app.repositories.config_repo import ConfigRepository


class _NoopSignalRepo:
    def find_recent_similar_by_entry_range(self, **kwargs):
        return []

    def find_recent_pass_main_same_side(self, **kwargs):
        return []


class _NoopMarketRepo:
    def find_active_around(self, *args, **kwargs):
        return []


def _load_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.rglob("*.json") if path.is_file())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay payload JSON files through normalizer + filter engine")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config-db-key", default="signal_bot_config")
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--persist", default="false")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    files = _load_paths(input_path)
    dry_run = str(args.dry_run).lower() == "true"
    persist = str(args.persist).lower() == "true"

    config = ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG
    engine = FilterEngine(config, _NoopSignalRepo(), _NoopMarketRepo())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for file_path in files:
            try:
                payload_dict = json.loads(file_path.read_text(encoding="utf-8"))
                payload = TradingViewWebhookPayload.model_validate(payload_dict)
                norm = SignalNormalizer.normalize("replay", payload)
                result = engine.run(norm)
                record = {
                    "file": str(file_path),
                    "status": "ok",
                    "signal_id": norm["signal_id"],
                    "decision": result.final_decision.value,
                    "route": result.route.value,
                    "decision_reason": result.decision_reason,
                    "config_db_key": args.config_db_key,
                    "dry_run": dry_run,
                    "persisted": False if not persist else False,
                }
            except Exception as exc:
                record = {
                    "file": str(file_path),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            out.write(json.dumps(record) + "\n")
    print(f"ok replayed {len(files)} payload(s) -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
