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


def test_summarize_compare_records_counts_decision_changes() -> None:
    from app.services.replay_service import summarize_compare_records

    records = [
        {"status": "ok", "decision_changed": True, "current_route": "MAIN", "proposed_route": "WARN", "current_decision": "PASS_MAIN", "proposed_decision": "PASS_WARNING"},
        {"status": "ok", "decision_changed": True, "current_route": "MAIN", "proposed_route": "NONE", "current_decision": "PASS_MAIN", "proposed_decision": "REJECT"},
        {"status": "ok", "decision_changed": True, "current_route": "NONE", "proposed_route": "MAIN", "current_decision": "REJECT", "proposed_decision": "PASS_MAIN"},
        {"status": "ok", "decision_changed": False, "current_route": "MAIN", "proposed_route": "MAIN", "current_decision": "PASS_MAIN", "proposed_decision": "PASS_MAIN"},
        {"status": "error"},
    ]

    summary = summarize_compare_records(records)

    assert summary["total"] == 5
    assert summary["changed_decisions"] == 3
    assert summary["main_to_warn"] == 1
    assert summary["pass_to_reject"] == 1
    assert summary["reject_to_pass"] == 1


def test_summarize_compare_records_handles_empty_list() -> None:
    from app.services.replay_service import summarize_compare_records

    summary = summarize_compare_records([])

    assert summary["total"] == 0
    assert summary["changed_decisions"] == 0
