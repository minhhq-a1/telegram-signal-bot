#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.repositories.config_repo import ConfigRepository
from app.services.replay_service import ReplayService, load_json_payloads


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
    dry_run = str(args.dry_run).lower() == "true"
    persist = str(args.persist).lower() == "true"

    config = ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG
    service = ReplayService(config)
    payloads = load_json_payloads(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for file_path, payload_dict in payloads:
            record = service.replay_payload(payload_dict, file_label=str(file_path))
            record["config_db_key"] = args.config_db_key
            record["dry_run"] = dry_run
            record["persisted"] = False if not persist else False
            out.write(json.dumps(record) + "\n")
    print(f"ok replayed {len(payloads)} payload(s) -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
