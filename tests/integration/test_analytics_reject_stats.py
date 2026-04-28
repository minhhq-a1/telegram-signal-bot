"""Integration tests for GET /api/v1/analytics/reject-stats.

Verifies the reject-stats endpoint contract:
- Without group_by: returns total rejects
- With group_by=reject_code: each REJECT signal counted once, by primary FAIL severity
- With group_by=signal_type,reject_code: correct bucketing, deduped
- Primary FAIL chosen by severity (CRITICAL > HIGH > MEDIUM > LOW)
- Auth required
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.enums import AuthStatus, DecisionType, RuleResult, RuleSeverity, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalFilterResult, WebhookEvent


def _seed_reject_signal(
    db_session,
    signal_id: str,
    signal_type: str,
    fail_rules: list[tuple[str, RuleSeverity]],
    side: str = "SHORT",
) -> Signal:
    """Seed a REJECT signal with given filter FAIL rules.

    Args:
        db_session: SQLAlchemy session
        signal_id: unique signal_id
        signal_type: e.g. SHORT_SQUEEZE, LONG_V73
        fail_rules: list of (rule_code, severity) for FAIL filter results
        side: LONG or SHORT
    """
    now = datetime.now(timezone.utc)

    raw_payload = {
        "secret": "test-secret",
        "signal_id": signal_id,
        "signal": side.lower(),
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "timestamp": "2026-04-18T15:30:00Z",
        "bar_time": "2026-04-18T15:30:00Z",
        "price": 68250.5,
        "source": "Bot_Webhook_v84",
        "confidence": 0.82,
        "metadata": {
            "entry": 68250.5,
            "stop_loss": 68650.0,
            "take_profit": 67000.0,
            "signal_type": signal_type,
            "strategy": "KELTNER_SQUEEZE",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "BREAKOUT_IMMINENT",
            "squeeze_fired": 0,
            "mom_direction": -1,
            "rsi": 45.0,
            "rsi_slope": -5.0,
            "kc_position": 0.30,
            "atr_pct": 0.264,
            "atr_percentile": 65.0,
            "adx": 21.4,
            "atr": 180.3,
            "stoch_k": 12.8,
            "vol_ratio": 1.24,
            "bar_confirmed": True,
        },
    }

    webhook_event = WebhookEvent(
        id=str(uuid.uuid4()),
        received_at=now,
        source_ip="127.0.0.1",
        http_headers={},
        raw_body=raw_payload,
        is_valid_json=True,
        auth_status=AuthStatus.OK,
        error_message=None,
    )
    db_session.add(webhook_event)
    db_session.flush()

    signal = Signal(
        id=str(uuid.uuid4()),
        webhook_event_id=webhook_event.id,
        signal_id=signal_id,
        source="Bot_Webhook_v84",
        symbol="BTCUSDT",
        timeframe="5m",
        side=side,
        price=68250.5,
        entry_price=68250.5,
        stop_loss=68650.0,
        take_profit=67000.0,
        risk_reward=1.81,
        indicator_confidence=0.82,
        signal_type=signal_type,
        strategy="KELTNER_SQUEEZE",
        regime="WEAK_TREND_DOWN",
        vol_regime="BREAKOUT_IMMINENT",
        mom_direction=-1,
        raw_payload=raw_payload,
        created_at=now,
    )
    db_session.add(signal)
    db_session.flush()

    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=signal.id,
        decision=DecisionType.REJECT,
        decision_reason="Rejected by filter engine",
        telegram_route=TelegramRoute.NONE,
        created_at=now,
    ))

    for rule_code, severity in fail_rules:
        db_session.add(SignalFilterResult(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            rule_code=rule_code,
            rule_group="strategy",
            result=RuleResult.FAIL,
            severity=severity,
            score_delta=0.0,
            details={},
            created_at=now,
        ))

    db_session.commit()
    return signal


class TestRejectStatsAuth:
    def test_reject_stats_no_auth_returns_401(self, client, db_session, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        response = client.get("/api/v1/analytics/reject-stats")
        assert response.status_code == 401

    def test_reject_stats_correct_auth_returns_200(self, client, db_session, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        response = client.get(
            "/api/v1/analytics/reject-stats",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200


class TestRejectStatsNoGroupBy:
    def test_reject_stats_empty_returns_total_zero(self, client, db_session, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        response = client.get(
            "/api/v1/analytics/reject-stats",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "total_rejects" in body
        assert body["total_rejects"] == 0
        assert body["buckets"] == []


class TestRejectStatsDedup:
    def test_single_reject_signal_counts_once_despite_multiple_fail_rules(
        self, client, db_session, monkeypatch
    ):
        """A REJECT signal with FAIL HIGH + FAIL LOW should contribute count=1, not 2."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        # Signal has two FAIL rules: SQ_NO_FIRED (HIGH) + SQ_BAD_MOM_DIRECTION (LOW)
        _seed_reject_signal(
            db_session,
            signal_id="dedup-multi-fail-001",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[
                ("SQ_NO_FIRED", RuleSeverity.HIGH),
                ("SQ_BAD_MOM_DIRECTION", RuleSeverity.LOW),
            ],
        )

        response = client.get(
            "/api/v1/analytics/reject-stats?group_by=reject_code",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200
        body = response.json()

        # Should have exactly one bucket (from the most severe FAIL: SQ_NO_FIRED → SQ_NO_FIRED)
        assert len(body["buckets"]) == 1
        bucket = body["buckets"][0]
        assert bucket["reject_code"] == "SQ_NO_FIRED"
        assert bucket["count"] == 1

    def test_multiple_reject_signals_each_counted_once(
        self, client, db_session, monkeypatch
    ):
        """Two REJECT signals should each contribute count=1 to their respective buckets."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        # Signal 1: SHORT_SQUEEZE, FAIL HIGH (SQ_NO_FIRED)
        _seed_reject_signal(
            db_session,
            signal_id="dedup-multi-signal-001",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[("SQ_NO_FIRED", RuleSeverity.HIGH)],
        )

        # Signal 2: SHORT_SQUEEZE, FAIL HIGH (SQ_NO_FIRED)
        _seed_reject_signal(
            db_session,
            signal_id="dedup-multi-signal-002",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[("SQ_NO_FIRED", RuleSeverity.HIGH)],
        )

        response = client.get(
            "/api/v1/analytics/reject-stats?group_by=reject_code",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200
        body = response.json()

        assert len(body["buckets"]) == 1
        assert body["buckets"][0]["reject_code"] == "SQ_NO_FIRED"
        assert body["buckets"][0]["count"] == 2


class TestRejectStatsGroupBy:
    def test_group_by_signal_type_and_reject_code(
        self, client, db_session, monkeypatch
    ):
        """group_by=signal_type,reject_code should return correct buckets per dimension."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        # 2 SHORT_SQUEEZE rejects (both SQ_NO_FIRED)
        _seed_reject_signal(
            db_session,
            signal_id="group-by-ss-001",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[("SQ_NO_FIRED", RuleSeverity.HIGH)],
        )
        _seed_reject_signal(
            db_session,
            signal_id="group-by-ss-002",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[("SQ_NO_FIRED", RuleSeverity.HIGH)],
        )

        # 1 LONG_V73 reject
        _seed_reject_signal(
            db_session,
            signal_id="group-by-lv-001",
            signal_type="LONG_V73",
            fail_rules=[("L_BASE_BAD_STRATEGY_NAME", RuleSeverity.HIGH)],
            side="LONG",
        )

        response = client.get(
            "/api/v1/analytics/reject-stats?group_by=signal_type,reject_code",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200
        body = response.json()

        assert body["period_days"] == 7
        buckets = {tuple(sorted(b.items())): b for b in body["buckets"]}

        # Extract counts
        count_map = {}
        for b in body["buckets"]:
            st = b.get("signal_type")
            rc = b.get("reject_code")
            count_map[(st, rc)] = b["count"]

        assert count_map.get(("SHORT_SQUEEZE", "SQ_NO_FIRED")) == 2
        assert count_map.get(("LONG_V73", "L_BASE_BAD_STRATEGY_NAME")) == 1

    def test_group_by_signal_type_only(self, client, db_session, monkeypatch):
        """group_by=signal_type should aggregate by signal_type alone."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        _seed_reject_signal(
            db_session,
            signal_id="group-by-st-001",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[("SQ_NO_FIRED", RuleSeverity.HIGH)],
        )
        _seed_reject_signal(
            db_session,
            signal_id="group-by-st-002",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[("SQ_BAD_MOM_DIRECTION", RuleSeverity.LOW)],
        )
        _seed_reject_signal(
            db_session,
            signal_id="group-by-st-003",
            signal_type="LONG_V73",
            fail_rules=[("L_BASE_BAD_STRATEGY_NAME", RuleSeverity.HIGH)],
            side="LONG",
        )

        response = client.get(
            "/api/v1/analytics/reject-stats?group_by=signal_type",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200
        body = response.json()

        count_map = {b["signal_type"]: b["count"] for b in body["buckets"]}
        assert count_map.get("SHORT_SQUEEZE") == 2
        assert count_map.get("LONG_V73") == 1


class TestRejectStatsSeverityPriority:
    def test_primary_fail_is_most_severe_despite_order(
        self, client, db_session, monkeypatch
    ):
        """Signal with FAIL LOW before FAIL CRITICAL should count CRITICAL, not LOW."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

        # Seed order: LOW added first, CRITICAL added second (but severity wins)
        signal = _seed_reject_signal(
            db_session,
            signal_id="severity-priority-001",
            signal_type="SHORT_SQUEEZE",
            fail_rules=[
                ("SQ_BAD_MOM_DIRECTION", RuleSeverity.LOW),    # less severe
                ("SQ_NO_FIRED", RuleSeverity.CRITICAL),         # most severe — should win
            ],
        )

        response = client.get(
            "/api/v1/analytics/reject-stats?group_by=reject_code",
            headers={"Authorization": "Bearer test-dash-token"},
        )
        assert response.status_code == 200
        body = response.json()

        # CRITICAL (SQ_NO_FIRED) should be the primary, not LOW (SQ_BAD_MOM_DIRECTION)
        assert len(body["buckets"]) == 1
        assert body["buckets"][0]["reject_code"] == "SQ_NO_FIRED"
        assert body["buckets"][0]["count"] == 1
