from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.domain.models import Signal, WebhookEvent

def test_webhook_accepted_valid_payload(client: TestClient, valid_payload: dict):
    """
    Test case: Webhook controller processes a valid payload successfully
    """
    response = client.post("/api/v1/webhooks/tradingview", json=valid_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["signal_id"] == valid_payload["signal_id"]
    assert "decision" in data
    assert "timestamp" in data

def test_webhook_rejected_invalid_secret(client: TestClient, valid_payload: dict):
    """
    Test case: Reject requests with an invalid secret
    """
    payload = valid_payload.copy()
    payload["secret"] = "wrong-secret"
    
    response = client.post("/api/v1/webhooks/tradingview", json=payload)
    
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "INVALID_SECRET"

def test_webhook_idempotency_duplicate_signal(client: TestClient, valid_payload: dict):
    """
    Test case: Duplicate signals should not be re-processed but return 200 DUPLICATE
    """
    # 1. First request
    response1 = client.post("/api/v1/webhooks/tradingview", json=valid_payload)
    assert response1.status_code == 200

    # 2. Second request with same signal_id
    response2 = client.post("/api/v1/webhooks/tradingview", json=valid_payload)
    assert response2.status_code == 200
    assert response2.json()["decision"] == "DUPLICATE"

def test_webhook_unsupported_timeframe(client: TestClient, valid_payload: dict):
    """
    Test case: Unsupported timeframe must be rejected by filter routing.
    """
    payload = valid_payload.copy()
    payload["timeframe"] = "30S"
    payload["signal_id"] = "tv-btcusdt-30s-special"

    response = client.post("/api/v1/webhooks/tradingview", json=payload)

    # Unsupported timeframe is handled in filter/persist flow => HTTP 200 with REJECT decision.
    assert response.status_code == 200
    assert response.json()["decision"] == "REJECT"


def test_webhook_missing_signal_id_is_accepted_with_generated_signal_id(
    client: TestClient,
    db_session,
    valid_payload: dict,
):
    payload = valid_payload.copy()
    payload.pop("signal_id")

    response = client.post("/api/v1/webhooks/tradingview", json=payload)

    assert response.status_code == 200
    response_payload = response.json()
    assert response_payload["status"] == "accepted"
    assert response_payload["signal_id"].startswith("tv-btcusdt-5m-")

    event = db_session.query(WebhookEvent).one()
    assert event.is_valid_json is True
    assert event.error_message is None


def test_webhook_normalizes_tradingview_minute_timeframe_and_generated_signal_id(
    client: TestClient,
    db_session,
    valid_payload: dict,
):
    payload = valid_payload.copy()
    payload.pop("signal_id")
    payload["timeframe"] = "3"

    response = client.post("/api/v1/webhooks/tradingview", json=payload)

    assert response.status_code == 200
    response_payload = response.json()
    assert response_payload["signal_id"].startswith("tv-btcusdt-3m-")

    signal = db_session.query(Signal).one()
    assert signal.timeframe == "3m"


def test_webhook_generated_signal_id_still_provides_deterministic_idempotency(
    client: TestClient,
    valid_payload: dict,
):
    payload = valid_payload.copy()
    payload.pop("signal_id")

    response1 = client.post("/api/v1/webhooks/tradingview", json=payload)
    response2 = client.post("/api/v1/webhooks/tradingview", json=payload)

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["signal_id"] == response2.json()["signal_id"]
    assert response2.json()["decision"] == "DUPLICATE"


def test_webhook_duplicate_race_returns_duplicate_without_500(
    client: TestClient,
    db_session,
    monkeypatch,
    valid_payload: dict,
):
    from app.api import webhook_controller

    existing_signal = Signal(
        id="existing-signal-row",
        webhook_event_id=None,
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
    )
    db_session.add(existing_signal)
    db_session.commit()

    lookup_counter = {"count": 0}

    original_find = webhook_controller.SignalRepository.find_by_signal_id

    def fake_find_by_signal_id(self, signal_id: str):
        lookup_counter["count"] += 1
        if lookup_counter["count"] == 1:
            return None
        return original_find(self, signal_id)

    def fake_create(self, data: dict):
        raise IntegrityError(
            "INSERT INTO signals ...",
            {},
            Exception("UNIQUE constraint failed: signals.signal_id"),
        )

    async def fail_if_called(self, route: str, text: str):
        raise AssertionError("Telegram notify must not run for duplicate race")

    monkeypatch.setattr(webhook_controller.SignalRepository, "find_by_signal_id", fake_find_by_signal_id)
    monkeypatch.setattr(webhook_controller.SignalRepository, "create", fake_create)
    monkeypatch.setattr(webhook_controller.TelegramNotifier, "notify", fail_if_called)

    response = client.post("/api/v1/webhooks/tradingview", json=valid_payload)

    assert response.status_code == 200
    assert response.json()["decision"] == "DUPLICATE"
    assert db_session.query(Signal).count() == 1
    assert db_session.query(WebhookEvent).count() == 1


def test_source_ip_ignores_spoofed_x_forwarded_for(client, db_session, valid_payload):
    """source_ip must use uvicorn-resolved request.client.host, not raw X-Forwarded-For.
    A client supplying its own X-Forwarded-For header must not poison source_ip.
    """
    from sqlalchemy import select
    from app.domain.models import WebhookEvent
    client.post(
        "/api/v1/webhooks/tradingview",
        json=valid_payload,
        headers={"X-Forwarded-For": "1.3.3.7, 10.0.0.1"},
    )
    event = db_session.execute(select(WebhookEvent)).scalars().first()
    # TestClient connects from 127.0.0.1 (testclient) — uvicorn resolves client.host
    # to that, ignoring the spoofed X-Forwarded-For. Must NOT be 1.3.3.7.
    assert event.source_ip != "1.3.3.7"
