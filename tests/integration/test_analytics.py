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
    resp = client.get("/api/v1/analytics/summary")
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

    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 2
    assert data["decisions"].get("PASS_MAIN") == 1
    assert data["telegram_delivery"].get("SENT") == 1


def test_summary_rejects_days_out_of_range(client: TestClient):
    assert client.get("/api/v1/analytics/summary?days=0").status_code == 422
    assert client.get("/api/v1/analytics/summary?days=91").status_code == 422
