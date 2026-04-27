"""E2E pipeline tests cho V1.1 integration.

These tests verify the full webhook → filter → decision pipeline with V1.1 rules.
Run with: pytest tests/integration/test_v11_pipeline.py
Requires: INTEGRATION_DATABASE_URL environment variable set.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlalchemy import select

from app.core.enums import DecisionType
from app.domain.models import Signal, SignalDecision, SignalFilterResult
from app.api import webhook_controller


def _load_payload(name: str) -> dict:
    return json.loads(Path(__file__).parent.parent.parent.joinpath(
        f"docs/examples/v11_sample_payloads/{name}.json"
    ).read_text())


@pytest.fixture
def v11_config():
    return {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
        "confidence_thresholds": {"15m": 0.74},
        "cooldown_minutes": {"15m": 25},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.002,
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


def test_short_squeeze_pass_e2e(client, db_session, monkeypatch, v11_config):
    """SHORT_SQUEEZE ideal signal → PASS_MAIN"""
    monkeypatch.setattr(
        webhook_controller.ConfigRepository,
        "get_signal_bot_config",
        lambda self: v11_config,
    )

    def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 123}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    payload = _load_payload("short_squeeze_pass")
    response = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in ("PASS_MAIN", "PASS_WARNING")


def test_short_squeeze_not_fired_e2e(client, db_session, monkeypatch, v11_config):
    """SHORT_SQUEEZE squeeze_fired=0 → REJECT"""
    monkeypatch.setattr(
        webhook_controller.ConfigRepository,
        "get_signal_bot_config",
        lambda self: v11_config,
    )

    def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 456}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    payload = _load_payload("short_squeeze_fail_not_fired")
    response = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "REJECT"

    # Verify reject_code surfaced in admin message
    from app.domain.models import TelegramMessage
    msgs = db_session.execute(select(TelegramMessage)).scalars().all()
    assert len(msgs) == 1
    assert "SQ_NO_FIRED" in msgs[0].message_text


def test_long_v73_pass_e2e(client, db_session, monkeypatch, v11_config):
    """LONG_V73 ideal signal → PASS_MAIN"""
    monkeypatch.setattr(
        webhook_controller.ConfigRepository,
        "get_signal_bot_config",
        lambda self: v11_config,
    )

    def fake_notify(self, route, text):
        return ("SENT", {"result": {"message_id": 789}}, None)

    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fake_notify)

    payload = _load_payload("long_v73_pass")
    response = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in ("PASS_MAIN", "PASS_WARNING")
