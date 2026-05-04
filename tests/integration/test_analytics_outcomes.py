from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.enums import DecisionType, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalOutcome, WebhookEvent

pytestmark = pytest.mark.integration


def _make_webhook(db_session: Session) -> WebhookEvent:
    wh = WebhookEvent(id=str(uuid.uuid4()), raw_body={}, auth_status="OK")
    db_session.add(wh)
    db_session.flush()
    return wh


def _make_signal(db_session: Session, webhook: WebhookEvent, signal_id: str, decision: str, strategy: str = "RSI_STOCH_V73") -> Signal:
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
        signal_type="LONG_V73",
        strategy=strategy,
        regime="WEAK_TREND_DOWN",
        vol_regime="TRENDING_LOW_VOL",
        raw_payload={},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(sig)
    db_session.flush()
    db_session.add(
        SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            decision=decision,
            decision_reason="seeded",
            telegram_route=TelegramRoute.MAIN if decision == DecisionType.PASS_MAIN else TelegramRoute.WARN,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    return sig


def _add_outcome(db_session: Session, signal: Signal, outcome_status: str, r_multiple: float | None = None, pnl_pct: float | None = None):
    db_session.add(
        SignalOutcome(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            outcome_status=outcome_status,
            close_reason="TP_HIT" if r_multiple and r_multiple > 0 else "SL_HIT",
            is_win=(r_multiple > 0) if r_multiple is not None else None,
            entry_price=68000.0,
            stop_loss=67500.0,
            take_profit=69000.0,
            pnl_pct=pnl_pct,
            r_multiple=r_multiple,
            exit_price=69000.0 if r_multiple and r_multiple > 0 else 67500.0,
            opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc) if outcome_status == "CLOSED" else None,
            created_at=datetime.now(timezone.utc),
        )
    )


def test_outcome_summary_empty(client):
    resp = client.get("/api/v1/analytics/outcomes/summary", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["closed_outcomes"] == 0
    assert body["open_outcomes"] == 0
    assert body["win_rate"] == 0.0


def test_outcome_summary_returns_aggregates(client, db_session: Session):
    wh = _make_webhook(db_session)
    sig1 = _make_signal(db_session, wh, "sig-1", DecisionType.PASS_MAIN)
    sig2 = _make_signal(db_session, wh, "sig-2", DecisionType.PASS_WARNING)
    sig3 = _make_signal(db_session, wh, "sig-3", DecisionType.PASS_WARNING)
    _add_outcome(db_session, sig1, "CLOSED", r_multiple=1.5, pnl_pct=1.2)
    _add_outcome(db_session, sig2, "CLOSED", r_multiple=-1.0, pnl_pct=-0.8)
    _add_outcome(db_session, sig3, "OPEN")
    db_session.commit()

    resp = client.get("/api/v1/analytics/outcomes/summary", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["closed_outcomes"] == 2
    assert body["open_outcomes"] == 1
    assert body["win_rate"] == 0.5
    assert body["total_r_multiple"] == 0.5
    assert body["by_decision"]["PASS_MAIN"]["count"] == 1


def test_outcome_bucket_invalid_group_by_returns_400(client):
    resp = client.get("/api/v1/analytics/outcomes/by-bucket?group_by=bad", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 400


def test_outcome_bucket_groups_by_timeframe_and_signal_type(client, db_session: Session):
    wh = _make_webhook(db_session)
    sig = _make_signal(db_session, wh, "sig-bucket", DecisionType.PASS_MAIN)
    _add_outcome(db_session, sig, "CLOSED", r_multiple=1.0, pnl_pct=0.9)
    db_session.commit()

    resp = client.get("/api/v1/analytics/outcomes/by-bucket?group_by=timeframe,signal_type", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["buckets"][0]["timeframe"] == "5m"
    assert body["buckets"][0]["signal_type"] == "LONG_V73"


def test_outcome_rules_returns_rule_metrics(client, db_session: Session):
    from app.domain.models import SignalFilterResult
    from app.core.enums import RuleResult, RuleSeverity

    wh = _make_webhook(db_session)
    sig = _make_signal(db_session, wh, "sig-rule", DecisionType.PASS_WARNING)
    _add_outcome(db_session, sig, "CLOSED", r_multiple=-0.5, pnl_pct=-0.2)
    db_session.add(
        SignalFilterResult(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            rule_code="LOW_VOLUME_WARNING",
            rule_group="trading",
            result=RuleResult.WARN,
            severity=RuleSeverity.MEDIUM,
            score_delta=0.0,
            details={},
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/analytics/outcomes/rules", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200, resp.json()
    row = resp.json()["rules"][0]
    assert row["rule_code"] == "LOW_VOLUME_WARNING"
    assert row["closed_outcomes"] == 1
