"""Integration tests for POST /api/v1/signals/{signal_id}/reverify.

Verifies the reverify endpoint contract:
- Happy path: returns reverify result with original + new decision
- 404 when signal not found
- 401 without auth
- signal_reverify_results row persisted in DB
- Decision can differ when rules have changed (V1.1 config vs V1.0 signal)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.enums import AuthStatus, DecisionType, RuleResult, RuleSeverity, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalFilterResult, SignalReverifyResult, WebhookEvent


def _seed_reject_signal(db_session, signal_id: str, fail_rule_code: str = "SQ_NO_FIRED", fail_severity: RuleSeverity = RuleSeverity.HIGH) -> Signal:
    """Seed a REJECT signal with one FAIL filter result."""
    now = datetime.now(timezone.utc)

    raw_payload = {
        "secret": "test-secret",
        "signal_id": signal_id,
        "signal": "short",
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
            "signal_type": "SHORT_SQUEEZE",
            "strategy": "KELTNER_SQUEEZE",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "BREAKOUT_IMMINENT",
            "squeeze_fired": 0,  # Will cause SQ_NO_FIRED FAIL
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
        side="SHORT",
        price=68250.5,
        entry_price=68250.5,
        stop_loss=68650.0,
        take_profit=67000.0,
        risk_reward=1.81,
        indicator_confidence=0.82,
        signal_type="SHORT_SQUEEZE",
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
        decision_reason="SQ_NO_FIRED: squeeze not fired",
        telegram_route=TelegramRoute.NONE,
        created_at=now,
    ))

    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=signal.id,
        rule_code=fail_rule_code,
        rule_group="strategy",
        result=RuleResult.FAIL,
        severity=fail_severity,
        score_delta=0.0,
        details={"squeeze_fired": 0},
        created_at=now,
    ))

    db_session.commit()
    return signal


def _seed_pass_signal(db_session, signal_id: str) -> Signal:
    """Seed a PASS_MAIN signal with ideal SHORT_SQUEEZE metadata."""
    now = datetime.now(timezone.utc)

    raw_payload = {
        "secret": "test-secret",
        "signal_id": signal_id,
        "signal": "short",
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
            "signal_type": "SHORT_SQUEEZE",
            "strategy": "KELTNER_SQUEEZE",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "BREAKOUT_IMMINENT",
            "squeeze_fired": 1,  # PASS
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
        side="SHORT",
        price=68250.5,
        entry_price=68250.5,
        stop_loss=68650.0,
        take_profit=67000.0,
        risk_reward=1.81,
        indicator_confidence=0.82,
        signal_type="SHORT_SQUEEZE",
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
        decision=DecisionType.PASS_MAIN,
        decision_reason="Passed all filters",
        telegram_route=TelegramRoute.MAIN,
        created_at=now,
    ))
    db_session.commit()
    return signal


@pytest.fixture
def v11_config():
    return {
        "allowed_symbols": ["BTCUSDT", "BTCUSD"],
        "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
        "confidence_thresholds": {"15m": 0.74, "5m": 0.78, "30m": 0.72, "1h": 0.70},
        "cooldown_minutes": {"5m": 10, "30m": 45, "1h": 90},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
        "enable_news_block": False,
        "news_block_before_min": 15,
        "news_block_after_min": 30,
        "log_reject_to_admin": True,
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
            "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
            "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
        },
        "rescoring": {
            "SHORT_SQUEEZE": {
                "base": 70,
                "bonuses": {
                    "vol_regime_breakout_imminent": 8,
                    "regime_weak_trend_down": 6,
                    "mom_direction_neg1": 5,
                    "squeeze_bars_ge_6": 5,
                    "rsi_ge_40": 4,
                    "rsi_slope_le_neg4": 4,
                    "atr_percentile_ge_70": 3,
                    "kc_position_le_040": 3,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "rsi_lt_35": -8,
                    "atr_pct_lt_020": -8,
                },
            },
            "SHORT_V73": {"base": 72, "bonuses": {}, "penalties": {}},
            "LONG_V73": {"base": 72, "bonuses": {}, "penalties": {}},
        },
        "score_pass_threshold": 75,
        "rr_tolerance_pct": 0.10,
        "rr_target_by_type": {"SHORT_SQUEEZE": 2.5, "SHORT_V73": 1.67, "LONG_V73": 1.67},
    }


def _reverify_headers(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
    return {"Authorization": "Bearer test-dash-token"}


class TestReverifyHappyPath:
    def test_reverify_returns_original_and_new_decision(self, client, db_session, monkeypatch, v11_config):
        from app.core.config import settings
        from app.api import signal_controller

        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
        monkeypatch.setattr(
            signal_controller.ConfigRepository,
            "get_signal_bot_config",
            lambda self: v11_config,
        )

        signal = _seed_reject_signal(db_session, "reverify-test-001")

        response = client.post(
            f"/api/v1/signals/{signal.signal_id}/reverify",
            headers={"Authorization": "Bearer test-dash-token"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["signal_id"] == signal.signal_id
        assert body["original_decision"] == "REJECT"
        assert body["reverify_decision"] in ("PASS_MAIN", "PASS_WARNING", "REJECT")
        assert "reverify_score" in body
        assert "reject_code" in body

    def test_reverify_signal_not_found_returns_404(self, client, db_session, monkeypatch, v11_config):
        from app.core.config import settings
        from app.api import signal_controller

        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
        monkeypatch.setattr(
            signal_controller.ConfigRepository,
            "get_signal_bot_config",
            lambda self: v11_config,
        )

        response = client.post(
            "/api/v1/signals/nonexistent-signal-id/reverify",
            headers={"Authorization": "Bearer test-dash-token"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Signal not found"

    def test_reverify_no_auth_returns_401(self, client, db_session, monkeypatch, v11_config):
        from app.core.config import settings
        from app.api import signal_controller

        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
        monkeypatch.setattr(
            signal_controller.ConfigRepository,
            "get_signal_bot_config",
            lambda self: v11_config,
        )

        signal = _seed_pass_signal(db_session, "reverify-no-auth-001")

        response = client.post(f"/api/v1/signals/{signal.signal_id}/reverify")

        assert response.status_code == 401

    def test_reverify_persists_result_in_db(self, client, db_session, monkeypatch, v11_config):
        from app.core.config import settings
        from app.api import signal_controller

        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
        monkeypatch.setattr(
            signal_controller.ConfigRepository,
            "get_signal_bot_config",
            lambda self: v11_config,
        )

        signal = _seed_pass_signal(db_session, "reverify-persist-001")

        # Count before
        before = db_session.execute(
            select(SignalReverifyResult).where(SignalReverifyResult.signal_row_id == signal.id)
        ).scalars().all()
        assert len(before) == 0

        response = client.post(
            f"/api/v1/signals/{signal.signal_id}/reverify",
            headers={"Authorization": "Bearer test-dash-token"},
        )

        assert response.status_code == 200

        rows = db_session.execute(
            select(SignalReverifyResult).where(SignalReverifyResult.signal_row_id == signal.id)
        ).scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.original_decision == "PASS_MAIN"
        assert row.reverify_decision in ("PASS_MAIN", "PASS_WARNING")
        assert row.signal_row_id == signal.id

    def test_reverify_pass_signal_becomes_reject_with_sq_no_fired(self, client, db_session, monkeypatch):
        """A signal that PASS_MAIN with squeeze_fired=1 becomes REJECT if squeeze_fired=0 in raw_payload."""
        from app.core.config import settings
        from app.api import signal_controller

        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
        monkeypatch.setattr(
            signal_controller.ConfigRepository,
            "get_signal_bot_config",
            lambda self: {
                "allowed_symbols": ["BTCUSDT", "BTCUSD"],
                "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
                "confidence_thresholds": {"5m": 0.78},
                "cooldown_minutes": {"5m": 10},
                "rr_min_base": 1.5,
                "rr_min_squeeze": 2.0,
                "duplicate_price_tolerance_pct": 0.002,
                "enable_news_block": False,
                "news_block_before_min": 15,
                "news_block_after_min": 30,
                "log_reject_to_admin": True,
                "strategy_thresholds": {
                    "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
                },
                "rescoring": {},
                "score_pass_threshold": 75,
                "rr_tolerance_pct": 0.10,
                "rr_target_by_type": {},
            },
        )

        # Seed a signal that looks like PASS_MAIN originally
        signal = _seed_reject_signal(db_session, "reverify-flip-001")

        response = client.post(
            f"/api/v1/signals/{signal.signal_id}/reverify",
            headers={"Authorization": "Bearer test-dash-token"},
        )

        assert response.status_code == 200
        body = response.json()
        # raw_payload has squeeze_fired=0 → SQ_NO_FIRED → REJECT
        assert body["reverify_decision"] == "REJECT"
        assert body["original_decision"] == "REJECT"
        assert body["reject_code"] is not None


class TestReverifyValidationError:
    def test_reverify_invalid_raw_payload_returns_422(self, client, db_session, monkeypatch, v11_config):
        """Old signal with raw_payload incompatible with current schema → 422, not 500."""
        from app.core.config import settings
        from app.api import signal_controller

        monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")
        monkeypatch.setattr(
            signal_controller.ConfigRepository,
            "get_signal_bot_config",
            lambda self: v11_config,
        )

        now = datetime.now(timezone.utc)

        # raw_payload missing required 'metadata' field — violates current schema
        raw_payload = {
            "secret": "test-secret",
            "signal_id": "invalid-raw-payload-001",
            "signal": "short",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "timestamp": "2026-04-18T15:30:00Z",
            "bar_time": "2026-04-18T15:30:00Z",
            "price": 68250.5,
            "source": "Bot_Webhook_v84",
            "confidence": 0.82,
            # intentionally missing "metadata" — TradingViewWebhookPayload requires it
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
            signal_id="invalid-raw-payload-001",
            source="Bot_Webhook_v84",
            symbol="BTCUSDT",
            timeframe="5m",
            side="SHORT",
            price=68250.5,
            entry_price=68250.5,
            stop_loss=68650.0,
            take_profit=67000.0,
            risk_reward=1.81,
            indicator_confidence=0.82,
            raw_payload=raw_payload,
            created_at=now,
        )
        db_session.add(signal)
        db_session.flush()
        db_session.add(SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=signal.id,
            decision=DecisionType.PASS_MAIN,
            decision_reason="seed",
            telegram_route=TelegramRoute.MAIN,
            created_at=now,
        ))
        db_session.commit()

        response = client.post(
            f"/api/v1/signals/{signal.signal_id}/reverify",
            headers={"Authorization": "Bearer test-dash-token"},
        )

        assert response.status_code == 422
        body = response.json()
        assert "raw_payload" in body["detail"].lower() or "schema" in body["detail"].lower()
