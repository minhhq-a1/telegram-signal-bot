from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_replay_payloads_script_writes_jsonl(tmp_path: Path):
    sample = {
        "secret": "test-secret",
        "signal": "long",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "timestamp": "2026-04-18T15:30:00Z",
        "bar_time": "2026-04-18T15:30:00Z",
        "price": 68250.5,
        "source": "Bot_Webhook_v84",
        "confidence": 0.82,
        "metadata": {
            "entry": 68250.5,
            "stop_loss": 67980.0,
            "take_profit": 68740.0,
            "signal_type": "LONG_V73",
            "strategy": "RSI_STOCH_V73",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "TRENDING_LOW_VOL",
        },
    }
    input_dir = tmp_path / "payloads"
    input_dir.mkdir()
    payload_file = input_dir / "sample.json"
    payload_file.write_text(json.dumps(sample), encoding="utf-8")
    output_file = tmp_path / "replay.jsonl"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/replay_payloads.py",
            "--input",
            str(input_dir),
            "--output",
            str(output_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ok replayed 1 payload(s)" in completed.stdout
    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["status"] == "ok"
    assert row["decision"] in {"PASS_MAIN", "PASS_WARNING", "REJECT"}
