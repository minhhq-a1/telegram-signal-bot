"""Integration tests for /api/v1/analytics/* endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import AuthStatus, DecisionType, DeliveryStatus, RuleResult, RuleSeverity, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalFilterResult, TelegramMessage, WebhookEvent


def _make_webhook(db_session: Session) -> WebhookEvent:
    wh = WebhookEvent(
        id=str(uuid.uuid4()),
        raw_body={},
        auth_status=AuthStatus.OK,
    )
    db_session.add(wh)
    db_session.flush()
    return wh


def _make_signal(db_session: Session, webhook: WebhookEvent, signal_id: str | None = None, created_at: datetime | None = None) -> Signal:
    sig = Signal(
        id=str(uuid.uuid4()),
        webhook_event_id=webhook.id,
        signal_id=signal_id or str(uuid.uuid4()),
        source="Bot_Webhook_v84",
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        price=68000.0,
        entry_price=68000.0,
        stop_loss=67500.0,
        take_profit=69000.0,
        risk_reward=2.0,
        indicator_confidence=0.82,
        raw_payload={},
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(sig)
    db_session.flush()
    return sig


def test_summary_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/summary", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 0
    assert data["decisions"] == {}
    assert data["telegram_delivery"] == {}
    assert data["by_side"] == {}
    assert data["by_symbol"] == {}
    assert data["by_timeframe"] == {}
    assert data["by_strategy"] == {}
    assert data["avg_confidence"] == 0.0
    assert data["avg_server_score"] == 0.0


def test_summary_returns_correct_counts(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    sig1 = _make_signal(db_session, wh)
    sig2 = _make_signal(db_session, wh)

    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig1.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="ok",
        telegram_route=TelegramRoute.MAIN,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.add(TelegramMessage(
        id=str(uuid.uuid4()),
        signal_row_id=sig1.id,
        chat_id="main-chat",
        route=TelegramRoute.MAIN,
        message_text="msg",
        delivery_status=DeliveryStatus.SENT,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/summary", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 2
    assert data["decisions"].get("PASS_MAIN") == 1
    assert data["telegram_delivery"].get("SENT") == 1


def test_summary_rejects_days_out_of_range(client: TestClient):
    assert client.get("/api/v1/analytics/summary?days=0", headers={"Authorization": "Bearer test-dash-token"}).status_code == 422
    assert client.get("/api/v1/analytics/summary?days=91", headers={"Authorization": "Bearer test-dash-token"}).status_code == 422


def test_timeline_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/signals/timeline", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["signals"] == []


def test_timeline_returns_signals_with_decision(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    sig = _make_signal(db_session, wh, signal_id="timeline-sig-001")
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="ok",
        telegram_route=TelegramRoute.MAIN,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/signals/timeline", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["signals"][0]["signal_id"] == "timeline-sig-001"
    assert data["signals"][0]["decision"] == "PASS_MAIN"


def test_timeline_days_param_filters(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    old_time = datetime.now(timezone.utc) - timedelta(days=10)
    _make_signal(db_session, wh, signal_id="old-signal", created_at=old_time)
    db_session.commit()

    resp = client.get("/api/v1/analytics/signals/timeline?days=7", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


def test_filter_stats_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/filters/stats", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["filter_rules"] == {}


def test_filter_stats_returns_grouped_by_rule_code(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    sig = _make_signal(db_session, wh)
    now = datetime.now(timezone.utc)
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code="SYMBOL_ALLOWED",
        rule_group="validation",
        result=RuleResult.PASS,
        severity=RuleSeverity.INFO,
        score_delta=0.0,
        details={},
        created_at=now,
    ))
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code="SYMBOL_ALLOWED",
        rule_group="validation",
        result=RuleResult.FAIL,
        severity=RuleSeverity.INFO,
        score_delta=0.0,
        details={},
        created_at=now,
    ))
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code="CONFIDENCE_CHECK",
        rule_group="quality",
        result=RuleResult.PASS,
        severity=RuleSeverity.INFO,
        score_delta=0.0,
        details={},
        created_at=now,
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/filters/stats", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    rules = data["filter_rules"]
    assert rules["SYMBOL_ALLOWED"]["PASS"] == 1
    assert rules["SYMBOL_ALLOWED"]["FAIL"] == 1
    assert rules["CONFIDENCE_CHECK"]["PASS"] == 1


def test_daily_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/daily", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["daily"] == {}


def test_daily_returns_correct_day_buckets(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    day1 = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    sig1 = _make_signal(db_session, wh, signal_id="day1-sig", created_at=day1)
    sig2 = _make_signal(db_session, wh, signal_id="day2-sig", created_at=day2)
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig1.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="ok",
        telegram_route=TelegramRoute.MAIN,
        created_at=day1,
    ))
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig2.id,
        decision=DecisionType.REJECT,
        decision_reason="filtered",
        telegram_route=TelegramRoute.NONE,
        created_at=day2,
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/daily?days=30", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    data = resp.json()
    daily = data["daily"]
    assert "2026-04-20" in daily
    assert "2026-04-21" in daily
    assert daily["2026-04-20"]["PASS_MAIN"] == 1
    assert daily["2026-04-21"]["REJECT"] == 1
