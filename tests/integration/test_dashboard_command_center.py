from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import DecisionType, DeliveryStatus, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalOutcome, TelegramMessage, WebhookEvent

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")


def _make_webhook(db_session: Session, received_at: datetime | None = None) -> WebhookEvent:
    wh = WebhookEvent(
        id=str(uuid.uuid4()),
        raw_body={},
        auth_status="OK",
        received_at=received_at or datetime.now(timezone.utc),
    )
    db_session.add(wh)
    db_session.flush()
    return wh


def _make_signal(
    db_session: Session,
    webhook: WebhookEvent,
    signal_id: str,
    decision: str,
    route: str,
    created_at: datetime | None = None,
) -> Signal:
    sig = Signal(
        id=str(uuid.uuid4()),
        webhook_event_id=webhook.id,
        signal_id=signal_id,
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
        server_score=0.79,
        signal_type="LONG_V73",
        strategy="RSI_STOCH_V73",
        regime="WEAK_TREND_DOWN",
        vol_regime="TRENDING_LOW_VOL",
        raw_payload={},
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(sig)
    db_session.flush()
    db_session.add(
        SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            decision=decision,
            decision_reason="seeded",
            telegram_route=route,
            created_at=created_at or datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    return sig


def test_ops_command_center_requires_auth(client: TestClient):
    resp = client.get("/api/v1/analytics/ops-command-center")
    assert resp.status_code == 401


def test_ops_command_center_empty_shape(client: TestClient):
    resp = client.get("/api/v1/analytics/ops-command-center", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["ops_snapshot"]["total_signals"] == 0
    assert body["recent_signals"] == []
    assert body["recent_outcomes"] == []
    assert "health" in body
    assert "alerts" in body


def test_ops_command_center_returns_signal_and_outcome_data(client: TestClient, db_session: Session):
    now = datetime.now(timezone.utc)
    wh = _make_webhook(db_session, received_at=now - timedelta(minutes=10))
    sig = _make_signal(db_session, wh, "cmd-center-sig", DecisionType.PASS_MAIN, TelegramRoute.MAIN, created_at=now)
    db_session.add(
        TelegramMessage(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            chat_id="main-chat",
            route=TelegramRoute.MAIN,
            message_text="hello",
            delivery_status=DeliveryStatus.SENT,
            created_at=now,
        )
    )
    db_session.add(
        SignalOutcome(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            outcome_status="CLOSED",
            close_reason="TP_HIT",
            is_win=True,
            entry_price=68000.0,
            stop_loss=67500.0,
            take_profit=69000.0,
            pnl_pct=1.2,
            r_multiple=1.5,
            exit_price=69000.0,
            opened_at=now,
            closed_at=now,
            created_at=now,
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/analytics/ops-command-center", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["ops_snapshot"]["total_signals"] == 1
    assert body["ops_snapshot"]["closed_outcomes"] == 1
    assert body["ops_snapshot"]["win_rate"] == 1.0
    assert body["recent_signals"][0]["signal_id"] == "cmd-center-sig"
    assert body["recent_outcomes"][0]["signal_id"] == "cmd-center-sig"
