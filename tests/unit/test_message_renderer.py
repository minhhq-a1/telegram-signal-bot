from typing import Optional
import pytest
from app.services.message_renderer import MessageRenderer

def test_render_main_long_contains_key_info():
    signal = {"side": "LONG", "symbol": "BTCUSDT", "timeframe": "5m",
               "entry_price": 68250.5, "stop_loss": 67980.0, "take_profit": 68740.0,
               "risk_reward": 1.81, "indicator_confidence": 0.81,
               "signal_type": "LONG_V73", "regime": "WEAK_TREND_DOWN",
               "vol_regime": "TRENDING_LOW_VOL", "rsi": 31.2, "stoch_k": 12.8,
               "adx": 21.4, "atr_pct": 0.264, "source": "Bot_Webhook_v84"}
    text = MessageRenderer.render_main(signal, 0.84)
    assert "🟢" in text
    assert "LONG" in text
    assert "BTCUSDT" in text
    assert "5m" in text
    assert "81%" in text   # confidence
    assert "84%" in text   # score
    assert "expected_wr" not in text.lower()  # KHÔNG được có expected WR

def test_render_main_none_fields_show_na():
    signal = {"side": "LONG", "symbol": "BTCUSDT", "timeframe": "5m",
               "entry_price": 68250.5, "stop_loss": 67980.0, "take_profit": 68740.0,
               "risk_reward": None, "indicator_confidence": 0.80,
               "signal_type": None, "regime": None, "vol_regime": None,
               "rsi": None, "stoch_k": None, "adx": None, "atr_pct": None,
               "source": "Bot_Webhook_v84"}
    text = MessageRenderer.render_main(signal, 0.80)
    assert "N/A" in text   # None fields phải hiển thị N/A, không crash
    assert "Powered by Telegram Signal Bot V1" in text


def test_render_warning_appends_footer():
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSD",
        "timeframe": "3m",
        "signal_id": "sig-123",
        "risk_reward": 2.1,
        "indicator_confidence": 0.75,
        "regime": "STRONG_TREND_UP",
        "vol_regime": "BREAKOUT_IMMINENT",
    }

    text = MessageRenderer.render_warning(signal, 0.70, "COOLDOWN_ACTIVE")

    assert "WARNING" in text
    assert "Powered by Telegram Signal Bot V1" in text


def test_render_reject_admin_appends_footer():
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSD",
        "timeframe": "3m",
        "signal_id": "sig-456",
    }

    text = MessageRenderer.render_reject_admin(signal, "TIMEFRAME_ALLOWED")

    assert "REJECTED" in text
    assert "Powered by Telegram Signal Bot V1" in text


def test_render_warning_contains_key_info():
    signal = {
        "side": "SHORT",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "signal_id": "warn-signal-001",
        "risk_reward": 1.6,
        "indicator_confidence": 0.74,
        "regime": "RANGING",
        "vol_regime": "HIGH_VOL",
    }
    text = MessageRenderer.render_warning(signal, 0.71, "Low confidence")
    assert "ETHUSDT" in text
    assert "SHORT" in text
    assert "15m" in text
    assert "Low confidence" in text
    assert "74%" in text   # confidence
    assert "71%" in text   # score
    assert "warn-signal-001" in text


def test_render_warning_no_entry_sl_tp_block():
    signal = {
        "side": "LONG",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "signal_id": "warn-signal-002",
        "risk_reward": None,
        "indicator_confidence": 0.70,
        "regime": None,
        "vol_regime": None,
    }
    text = MessageRenderer.render_warning(signal, 0.65, "Weak trend")
    assert "Entry:" not in text
    assert "SL:" not in text
    assert "TP:" not in text


def test_render_reject_admin_contains_key_info():
    signal = {
        "side": "LONG",
        "symbol": "SOLUSDT",
        "timeframe": "1h",
        "signal_id": "reject-signal-001",
    }
    text = MessageRenderer.render_reject_admin(signal, "Below confidence threshold")
    assert "SOLUSDT" in text
    assert "LONG" in text
    assert "1h" in text
    assert "Below confidence threshold" in text
    assert "reject-signal-001" in text


def test_render_reject_admin_has_no_confidence_or_score():
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "signal_id": "reject-signal-002",
    }
    text = MessageRenderer.render_reject_admin(signal, "Cooldown active")
    assert "Conf:" not in text
    assert "Score:" not in text


def test_render_reject_admin_includes_reject_code():
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "signal_id": "sig-789",
    }
    text = MessageRenderer.render_reject_admin(
        signal, "Strategy validation failed: SQ_NO_FIRED", reject_code="SQ_NO_FIRED"
    )
    assert "RejectCode:" in text
    assert "SQ_NO_FIRED" in text


def test_render_reject_admin_no_code_when_none():
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "signal_id": "sig-999",
    }
    text = MessageRenderer.render_reject_admin(signal, "Some error", reject_code=None)
    assert "RejectCode:" not in text


def test_render_reject_admin_backward_compat_no_reject_code():
    """Existing calls without reject_code still work"""
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "signal_id": "sig-000",
    }
    text = MessageRenderer.render_reject_admin(signal, "TIMEFRAME_ALLOWED")
    assert "REJECTED" in text
    assert "TIMEFRAME_ALLOWED" in text
