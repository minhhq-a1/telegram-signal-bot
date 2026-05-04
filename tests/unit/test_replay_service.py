from __future__ import annotations

from app.repositories.config_repo import ConfigRepository
from app.services.replay_service import ReplayService


def _payload() -> dict:
    return {
        "secret": "x",
        "signal": "long",
        "symbol": "BTCUSDT",
        "timeframe": "5",
        "timestamp": "2026-05-02T00:00:00Z",
        "price": 100.0,
        "source": "test",
        "confidence": 0.9,
        "metadata": {"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "signal_type": "LONG_V73"},
    }


def test_replay_payload_returns_ok_record() -> None:
    service = ReplayService(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)

    record = service.replay_payload(_payload(), file_label="sample.json")

    assert record["status"] == "ok"
    assert record["file"] == "sample.json"
    assert record["decision"] in {"PASS_MAIN", "PASS_WARNING", "REJECT"}


def test_replay_payload_returns_error_record_for_invalid_payload() -> None:
    service = ReplayService(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)

    record = service.replay_payload({"bad": "payload"}, file_label="bad.json")

    assert record["status"] == "error"
    assert record["file"] == "bad.json"


def test_compare_payload_reports_decision_fields() -> None:
    service = ReplayService(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)
    proposed = {**ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG, "confidence_thresholds": {"5m": 0.95}}

    record = service.compare_payload(_payload(), proposed_config=proposed, file_label="sample.json")

    assert record["status"] == "ok"
    assert "current_decision" in record
    assert "proposed_decision" in record
    assert "changed_rule_codes" in record
