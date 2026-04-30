from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

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
            # V1.1 keys for Phase 2.5 strategy validation
            "rr_tolerance_pct": 0.10,
            "rr_target_by_type": {"SHORT_SQUEEZE": 2.5, "SHORT_V73": 1.67, "LONG_V73": 1.67},
            "strategy_thresholds": {
                "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
                "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
                "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
            },
            "rescoring": {},
            "score_pass_threshold": 75,
        },
    )

    async def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 12345}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    # Seed a prior PASS_MAIN signal with DIFFERENT side (LONG) so SHORT cooldown doesn't fire
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
        signal_id="prior-pass-main-logs-test",
        source=valid_payload["source"],
        symbol=valid_payload["symbol"],
        timeframe=valid_payload["timeframe"],
        side="SHORT",  # Different side from webhook (LONG) → no cooldown or duplicate interference
        price=valid_payload["price"],
        entry_price=valid_payload["metadata"]["entry"] + 100.0,  # Different entry → no DUPLICATE check match
        stop_loss=valid_payload["metadata"]["stop_loss"],
        take_profit=valid_payload["metadata"]["take_profit"],
        risk_reward=1.81,
        indicator_confidence=valid_payload["confidence"],
        raw_payload=valid_payload,
        created_at=now,
    )
    db_session.add(prior_signal)
    db_session.flush()
    prior_signal.created_at = now
    db_session.flush()
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=prior_signal.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="seed cooldown isolation",
        telegram_route=TelegramRoute.MAIN,
        created_at=now,
    ))
    db_session.commit()

    response = client.post("/api/v1/webhooks/tradingview", json=valid_payload)

    assert response.status_code == 200
    payload_resp = response.json()
    assert payload_resp["decision"] == "PASS_MAIN"

    telegram_logs = db_session.execute(select(TelegramMessage)).scalars().all()
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

    event = db_session.execute(select(WebhookEvent)).scalars().one()
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

    event = db_session.execute(select(WebhookEvent)).scalars().one()
    assert event.is_valid_json is False
    assert event.auth_status == AuthStatus.MISSING
    assert event.error_message == "INVALID_JSON: Request body is not valid JSON"
    assert event.raw_body["_raw_body_text"] == "***REDACTED***"
    assert event.correlation_id is not None


def test_webhook_pipeline_completed_log_includes_correlation_id(client, db_session, monkeypatch, valid_payload):
    from app.api import webhook_controller

    async def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 12345}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    with patch("app.services.webhook_ingestion_service.logger.info") as logger_info:
        response = client.post(
            "/api/v1/webhooks/tradingview",
            json=valid_payload,
            headers={"X-Correlation-ID": "corr-log-001"},
        )

    assert response.status_code == 200
    summary_calls = [
        call
        for call in logger_info.call_args_list
        if call.args and call.args[0] == "webhook_pipeline_completed"
    ]
    assert len(summary_calls) == 1

    summary_extra = summary_calls[0].kwargs["extra"]
    assert summary_extra["correlation_id"] == "corr-log-001"
    assert summary_extra["signal_id"] == valid_payload["signal_id"]
    assert summary_extra["decision"] == "PASS_MAIN"
    assert "secret" not in json.dumps(summary_extra)


def test_webhook_logs_invalid_schema_before_rejecting(client, db_session, valid_payload):
    invalid_payload = dict(valid_payload)
    invalid_payload.pop("price")
    invalid_payload["metadata"] = {
        **valid_payload["metadata"],
        "nested_token": "metadata-token-value",
        "auth": {"api_key": "nested-api-key-value"},
    }

    response = client.post(
        "/api/v1/webhooks/tradingview",
        json=invalid_payload,
        headers={"Authorization": "Bearer schema-secret-token"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_SCHEMA"

    event = db_session.execute(select(WebhookEvent)).scalars().one()
    assert event.is_valid_json is True
    assert event.auth_status == AuthStatus.MISSING
    assert event.error_message is not None
    assert event.error_message.startswith("INVALID_SCHEMA:")
    assert event.raw_body["symbol"] == valid_payload["symbol"]
    assert event.raw_body["secret"] == "***REDACTED***"
    assert event.raw_body["metadata"]["nested_token"] == "***REDACTED***"
    assert event.raw_body["metadata"]["auth"]["api_key"] == "***REDACTED***"
    assert event.http_headers["authorization"] == "***REDACTED***"


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
            "rr_tolerance_pct": 0.10,
            "rr_target_by_type": {"SHORT_SQUEEZE": 2.5, "SHORT_V73": 1.67, "LONG_V73": 1.67},
            "strategy_thresholds": {
                "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
                "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
                "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
            },
            "rescoring": {},
            "score_pass_threshold": 75,
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
        side="LONG",  # Same side as webhook (LONG) so cooldown can fire; entry offset -200.0 keeps price diff > 0.2% to avoid DUPLICATE firing first
        price=valid_payload["price"],
        entry_price=valid_payload["metadata"]["entry"] - 200.0,  # 0.293% diff > 0.2% tolerance → DUPLICATE won't fire
        stop_loss=valid_payload["metadata"]["stop_loss"] - 200.0,
        take_profit=valid_payload["metadata"]["take_profit"] - 200.0,
        risk_reward=1.81,
        indicator_confidence=valid_payload["confidence"],
        raw_payload=valid_payload,
        created_at=now,
    )
    db_session.add(prior_signal)
    db_session.flush()
    # Update created_at to NOW so cooldown window is active
    prior_signal.created_at = now
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
            "rr_tolerance_pct": 0.10,
            "rr_target_by_type": {"SHORT_SQUEEZE": 2.5, "SHORT_V73": 1.67, "LONG_V73": 1.67},
            "strategy_thresholds": {
                "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
                "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
                "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
            },
            "rescoring": {},
            "score_pass_threshold": 75,
        },
    )

    async def fake_failed_notify(self, route, text):
        return ("FAILED", None, "TimeoutException: timeout")

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_failed_notify)

    # Seed a prior PASS_MAIN signal on DIFFERENT timeframe so SHORT/5m cooldown doesn't fire
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
        signal_id="prior-telegram-failure-seed-1m",
        source=valid_payload["source"],
        symbol=valid_payload["symbol"],
        timeframe="1m",  # Different timeframe → no cooldown for 5m signals
        side="SHORT",
        price=valid_payload["price"],
        entry_price=valid_payload["metadata"]["entry"],
        stop_loss=valid_payload["metadata"]["stop_loss"],
        take_profit=valid_payload["metadata"]["take_profit"],
        risk_reward=1.81,
        indicator_confidence=valid_payload["confidence"],
        raw_payload=valid_payload,
        created_at=now,
    )
    db_session.add(prior_signal)
    db_session.flush()
    prior_signal.created_at = now
    db_session.flush()
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=prior_signal.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="seed isolation 1m",
        telegram_route=TelegramRoute.MAIN,
        created_at=now,
    ))
    db_session.commit()

    payload = dict(valid_payload)
    payload["signal_id"] = "telegram-failure-audit-001"

    response = client.post("/api/v1/webhooks/tradingview", json=payload)

    assert response.status_code == 200
    body = response.json()
    # No cooldown (different timeframe) → PASS_MAIN
    assert body["decision"] == "PASS_MAIN"

    signal = db_session.execute(select(Signal).where(Signal.signal_id == "telegram-failure-audit-001")).scalar_one_or_none()
    decision = db_session.execute(select(SignalDecision).where(SignalDecision.signal_row_id == signal.id)).scalar_one_or_none()
    telegram_log = db_session.execute(select(TelegramMessage).where(TelegramMessage.signal_row_id == signal.id)).scalar_one_or_none()

    assert decision.decision == DecisionType.PASS_MAIN
    assert telegram_log.delivery_status == DeliveryStatus.FAILED
    assert telegram_log.error_log == "TimeoutException: timeout"
