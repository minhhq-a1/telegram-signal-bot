from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.enums import AuthStatus, DecisionType, DeliveryStatus, RuleResult, RuleSeverity, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalFilterResult, TelegramMessage, WebhookEvent
from app.services.filter_engine import FilterExecutionResult


def test_webhook_pass_main_logs_telegram_delivery(client, db_session, monkeypatch, valid_payload):
    from app.api import webhook_controller

    monkeypatch.setattr(
        webhook_controller.ConfigRepository,
        "get_signal_bot_config",
        lambda self: {
            "allowed_symbols": ["BTCUSDT", "BTCUSD"],
            "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
            "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70},
            "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90},
            "rr_min_base": 1.5,
            "rr_min_squeeze": 2.0,
            "duplicate_price_tolerance_pct": 0.002,
            "news_block_before_min": 15,
            "news_block_after_min": 30,
            "log_reject_to_admin": True,
        },
    )

    async def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 12345}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    response = client.post("/api/v1/webhooks/tradingview", json=valid_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "PASS_MAIN"

    telegram_logs = db_session.query(TelegramMessage).all()
    assert len(telegram_logs) == 1
    assert telegram_logs[0].route == TelegramRoute.MAIN
    assert telegram_logs[0].delivery_status == DeliveryStatus.SENT


def test_webhook_rejects_invalid_timestamp_format_with_audit_row(client, db_session, valid_payload):
    invalid_payload = dict(valid_payload)
    invalid_payload["timestamp"] = "not-a-valid-iso-datetime"

    response = client.post("/api/v1/webhooks/tradingview", json=invalid_payload)

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_SCHEMA"

    event = db_session.query(WebhookEvent).one()
    assert event.is_valid_json is True
    assert event.auth_status == AuthStatus.MISSING
    assert event.error_message is not None
    assert event.error_message.startswith("INVALID_SCHEMA:")


def test_webhook_logs_invalid_json_before_rejecting(client, db_session):
    response = client.post(
        "/api/v1/webhooks/tradingview",
        content='{"signal_id": "broken", "signal": "long"',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_JSON"

    event = db_session.query(WebhookEvent).one()
    assert event.is_valid_json is False
    assert event.auth_status == AuthStatus.MISSING
    assert event.error_message == "INVALID_JSON: Request body is not valid JSON"
    assert event.raw_body["_raw_body_text"] == '{"signal_id": "broken", "signal": "long"'


def test_webhook_logs_invalid_schema_before_rejecting(client, db_session, valid_payload):
    invalid_payload = dict(valid_payload)
    invalid_payload.pop("price")

    response = client.post("/api/v1/webhooks/tradingview", json=invalid_payload)

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_SCHEMA"

    event = db_session.query(WebhookEvent).one()
    assert event.is_valid_json is True
    assert event.auth_status == AuthStatus.MISSING
    assert event.error_message is not None
    assert event.error_message.startswith("INVALID_SCHEMA:")
    assert event.raw_body["symbol"] == valid_payload["symbol"]


def test_get_signal_detail_returns_nested_contract(client, db_session):
    now = datetime.now(timezone.utc)

    signal = Signal(
        id=str(uuid.uuid4()),
        signal_id="sig-detail-001",
        source="Bot_Webhook_v84",
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        price=68250.5,
        entry_price=68250.5,
        stop_loss=67980.0,
        take_profit=68740.0,
        risk_reward=1.81,
        indicator_confidence=0.82,
        server_score=0.82,
        signal_type="LONG_V73",
        strategy="RSI_STOCH_V73",
        regime="WEAK_TREND_DOWN",
        vol_regime="TRENDING_LOW_VOL",
        raw_payload={"signal_id": "sig-detail-001"},
        created_at=now,
    )
    db_session.add(signal)
    db_session.flush()

    db_session.add(
        SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            decision=DecisionType.PASS_MAIN,
            decision_reason="Passed all filters",
            telegram_route=TelegramRoute.MAIN,
            created_at=now,
        )
    )
    db_session.add(
        SignalFilterResult(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            rule_code="SYMBOL_ALLOWED",
            rule_group="validation",
            result=RuleResult.PASS,
            severity=RuleSeverity.INFO,
            score_delta=0.0,
            details={"allowed": ["BTCUSDT", "BTCUSD"]},
            created_at=now,
        )
    )
    db_session.add(
        TelegramMessage(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            chat_id="main-chat",
            route=TelegramRoute.MAIN,
            message_text="test message",
            delivery_status=DeliveryStatus.SENT,
            sent_at=now,
            created_at=now,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/signals/sig-detail-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_id"] == "sig-detail-001"
    assert payload["signal"]["signal_id"] == "sig-detail-001"
    assert payload["decision"]["decision"] == "PASS_MAIN"
    assert payload["filter_results"][0]["details"] == {"allowed": ["BTCUSDT", "BTCUSD"]}
    assert payload["telegram_messages"][0]["channel_type"] == "MAIN"


def test_seeded_signal_bot_config_matches_v1_docs():
    migration_path = Path("migrations/001_init.sql")
    migration_text = migration_path.read_text(encoding="utf-8")

    match = re.search(
        r"'signal_bot_config',\s*'(\{.*?\})'::jsonb",
        migration_text,
        re.DOTALL,
    )
    assert match is not None, "Could not find seeded signal_bot_config JSON in migration"

    seeded_config = json.loads(match.group(1))

    assert seeded_config["allowed_symbols"] == ["BTCUSDT", "BTCUSD"]
    assert seeded_config["allowed_timeframes"] == ["1m", "3m", "5m", "12m", "15m", "30m", "1h"]
    assert seeded_config["confidence_thresholds"] == {
        "1m": 0.82,
        "3m": 0.80,
        "5m": 0.78,
        "12m": 0.76,
        "15m": 0.74,
        "30m": 0.72,
        "1h": 0.70,
    }
    assert seeded_config["cooldown_minutes"] == {
        "1m": 5,
        "3m": 8,
        "5m": 10,
        "12m": 20,
        "15m": 25,
        "30m": 45,
        "1h": 90,
    }
    assert seeded_config["enable_news_block"] is True


def test_webhook_duplicate_returns_valid_duplicate_response(client, db_session, monkeypatch, valid_payload):
    from app.api import webhook_controller

    now = datetime.now(timezone.utc)

    webhook_event = WebhookEvent(
        id=str(uuid.uuid4()),
        received_at=now,
        source_ip="127.0.0.1",
        http_headers={},
        raw_body=valid_payload,
        is_valid_json=True,
        auth_status=AuthStatus.OK,
        error_message=None,
    )
    db_session.add(webhook_event)
    db_session.flush()

    existing_signal = Signal(
        id=str(uuid.uuid4()),
        webhook_event_id=webhook_event.id,
        signal_id=valid_payload["signal_id"],
        source=valid_payload["source"],
        symbol=valid_payload["symbol"],
        timeframe=valid_payload["timeframe"],
        side="LONG",
        price=valid_payload["price"],
        entry_price=valid_payload["metadata"]["entry"],
        stop_loss=valid_payload["metadata"]["stop_loss"],
        take_profit=valid_payload["metadata"]["take_profit"],
        risk_reward=1.81,
        indicator_confidence=valid_payload["confidence"],
        raw_payload=valid_payload,
        created_at=now,
    )
    db_session.add(existing_signal)
    db_session.commit()

    response = client.post("/api/v1/webhooks/tradingview", json=valid_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["signal_id"] == valid_payload["signal_id"]
    assert payload["decision"] == "DUPLICATE"
    assert "timestamp" in payload


def test_webhook_invalid_secret_returns_documented_error_contract(client, valid_payload):
    invalid_payload = dict(valid_payload)
    invalid_payload["secret"] = "wrong-secret"

    response = client.post("/api/v1/webhooks/tradingview", json=invalid_payload)

    assert response.status_code == 401
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "INVALID_SECRET"
    assert "message" in payload


@pytest.mark.parametrize(
    ("prior_decision", "expected_decision"),
    [
        (DecisionType.REJECT, "PASS_MAIN"),
        (DecisionType.PASS_WARNING, "PASS_MAIN"),
        (DecisionType.PASS_MAIN, "PASS_WARNING"),
    ],
)
def test_cooldown_only_applies_to_prior_pass_main(
    client,
    db_session,
    monkeypatch,
    valid_payload,
    prior_decision,
    expected_decision,
):
    from app.api import webhook_controller

    monkeypatch.setattr(
        webhook_controller.ConfigRepository,
        "get_signal_bot_config",
        lambda self: {
            "allowed_symbols": ["BTCUSDT", "BTCUSD"],
            "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
            "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70},
            "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90},
            "rr_min_base": 1.5,
            "rr_min_squeeze": 2.0,
            "duplicate_price_tolerance_pct": 0.002,
            "news_block_before_min": 15,
            "news_block_after_min": 30,
            "log_reject_to_admin": True,
        },
    )

    async def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 99999}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    now = datetime.now(timezone.utc)

    prior_webhook_event = WebhookEvent(
        id=str(uuid.uuid4()),
        received_at=now,
        source_ip="127.0.0.1",
        http_headers={},
        raw_body=valid_payload,
        is_valid_json=True,
        auth_status=AuthStatus.OK,
        error_message=None,
    )
    db_session.add(prior_webhook_event)
    db_session.flush()

    prior_signal = Signal(
        id=str(uuid.uuid4()),
        webhook_event_id=prior_webhook_event.id,
        signal_id="prior-cooldown-signal",
        source=valid_payload["source"],
        symbol=valid_payload["symbol"],
        timeframe=valid_payload["timeframe"],
        side="LONG",
        price=valid_payload["price"],
        entry_price=valid_payload["metadata"]["entry"] - 200.0,
        stop_loss=valid_payload["metadata"]["stop_loss"] - 200.0,
        take_profit=valid_payload["metadata"]["take_profit"] - 200.0,
        risk_reward=1.81,
        indicator_confidence=valid_payload["confidence"],
        raw_payload=valid_payload,
        created_at=now,
    )
    db_session.add(prior_signal)
    db_session.flush()

    if prior_decision == DecisionType.PASS_MAIN:
        prior_route = TelegramRoute.MAIN
    elif prior_decision == DecisionType.PASS_WARNING:
        prior_route = TelegramRoute.WARN
    else:
        prior_route = TelegramRoute.NONE
    db_session.add(
        SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=prior_signal.id,
            decision=prior_decision,
            decision_reason=f"seed {prior_decision.value}",
            telegram_route=prior_route,
            created_at=now,
        )
    )
    db_session.commit()

    payload = dict(valid_payload)
    payload["signal_id"] = f"cooldown-{prior_decision.value.lower()}"
    payload["timestamp"] = "2026-04-18T15:31:00Z"
    payload["bar_time"] = "2026-04-18T15:31:00Z"

    response = client.post("/api/v1/webhooks/tradingview", json=payload)

    assert response.status_code == 200
    assert response.json()["decision"] == expected_decision


def test_telegram_total_failure_keeps_audit_and_error_log(client, db_session, monkeypatch, valid_payload):
    from app.api import webhook_controller

    monkeypatch.setattr(
        webhook_controller.ConfigRepository,
        "get_signal_bot_config",
        lambda self: {
            "allowed_symbols": ["BTCUSDT", "BTCUSD"],
            "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
            "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70},
            "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90},
            "rr_min_base": 1.5,
            "rr_min_squeeze": 2.0,
            "duplicate_price_tolerance_pct": 0.002,
            "news_block_before_min": 15,
            "news_block_after_min": 30,
            "log_reject_to_admin": True,
        },
    )

    async def fake_failed_notify(self, route, text):
        return ("FAILED", None, "TimeoutException: timeout")

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_failed_notify)

    payload = dict(valid_payload)
    payload["signal_id"] = "telegram-failure-audit-001"

    response = client.post("/api/v1/webhooks/tradingview", json=payload)

    assert response.status_code == 200
    assert response.json()["decision"] == "PASS_MAIN"

    signal = db_session.query(Signal).filter_by(signal_id="telegram-failure-audit-001").one()
    decision = db_session.query(SignalDecision).filter_by(signal_row_id=signal.id).one()
    telegram_log = db_session.query(TelegramMessage).filter_by(signal_row_id=signal.id).one()

    assert decision.decision == DecisionType.PASS_MAIN
    assert telegram_log.delivery_status == DeliveryStatus.FAILED
    assert telegram_log.error_log == "TimeoutException: timeout"
