from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
