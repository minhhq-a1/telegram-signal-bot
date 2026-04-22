from typing import Optional
import pytest
from app.services.signal_normalizer import SignalNormalizer
from app.domain.schemas import TradingViewWebhookPayload

def make_payload(**overrides) -> dict:
    base = {
        "secret": "abc",
        "signal_id": "test-id",
        "signal": "long",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "timestamp": "2026-04-18T15:30:00Z",
        "price": 68250.5,
        "source": "test",
        "confidence": 0.82,
        "metadata": {
            "entry": 68250.5,
            "stop_loss": 67980.0,
            "take_profit": 68740.0,
        }
    }
    # simple merge
    for k, v in overrides.items():
        if k == "metadata":
            base["metadata"].update(v)
        else:
            base[k] = v
    return base

def test_normalize_long_calculates_rr():
    payload_data = make_payload()
    payload = TradingViewWebhookPayload(**payload_data)
    normalized = SignalNormalizer.normalize("evt-123", payload)
    # risk = 68250.5 - 67980.0 = 270.5
    # reward = 68740.0 - 68250.5 = 489.5
    # rr = 489.5 / 270.5 ≈ 1.81
    assert abs(normalized["risk_reward"] - 1.81) < 0.01

def test_normalize_short_calculates_rr():
    payload_data = make_payload(signal="short", metadata={"entry": 68910.0, "stop_loss": 69121.0, "take_profit": 68277.0})
    payload = TradingViewWebhookPayload(**payload_data)
    normalized = SignalNormalizer.normalize("evt-123", payload)
    # risk = 69121 - 68910 = 211
    # reward = 68910 - 68277 = 633
    # rr ≈ 3.0
    assert abs(normalized["risk_reward"] - 3.0) < 0.1

def test_normalize_maps_side_to_uppercase():
    payload_data = make_payload(signal="long")
    payload = TradingViewWebhookPayload(**payload_data)
    normalized = SignalNormalizer.normalize("evt-123", payload)
    assert normalized["side"] == "LONG"

def test_normalize_rr_none_when_risk_zero():
    payload_data = make_payload(metadata={"entry": 68250.5, "stop_loss": 68250.5, "take_profit": 68740.0})
    payload = TradingViewWebhookPayload(**payload_data)
    normalized = SignalNormalizer.normalize("evt-123", payload)
    assert normalized["risk_reward"] is None


def test_payload_generates_signal_id_when_missing():
    payload_data = make_payload()
    payload_data.pop("signal_id")

    payload = TradingViewWebhookPayload(**payload_data)

    assert payload.signal_id is not None
    assert payload.signal_id.startswith("tv-btcusdt-5m-2026-04-18T15:30:00Z-long-")


def test_payload_normalizes_tradingview_native_minute_timeframe():
    payload = TradingViewWebhookPayload(**make_payload(timeframe="60"))
    assert payload.timeframe == "1h"
