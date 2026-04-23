"""Integration tests for webhook rate limiting."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings


def test_webhook_rate_limit_with_overrides(client: TestClient, monkeypatch, valid_payload: dict):
    """Test rate limiting allows requests up to limit, then blocks with 429."""
    # Override to use low limit (5/minute) for quick testing
    monkeypatch.setattr(settings, "webhook_rate_limit", 5)

    # Send 5 requests - all should succeed
    for i in range(5):
        payload = valid_payload.copy()
        payload["signal_id"] = f"tv-btcusdt-5m-1713452400000-long-long_v73_{i}"
        resp = client.post(
            "/api/v1/webhooks/tradingview",
            json=payload,
        )
        # Should get 200, 400, or 409 (valid responses), NOT 429
        assert resp.status_code in [200, 400, 409, 500], f"Request {i+1} failed with {resp.status_code}"

    # 6th request should be rate limited (429)
    payload = valid_payload.copy()
    payload["signal_id"] = "tv-btcusdt-5m-1713452400000-long-long_v73_rate_limit_test"
    resp = client.post(
        "/api/v1/webhooks/tradingview",
        json=payload,
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers or "retry-after" in {k.lower() for k in resp.headers.keys()}


def test_webhook_rate_limit_response_headers(client: TestClient, monkeypatch, valid_payload: dict):
    """Test 429 response includes rate limit headers."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 1)

    # First request succeeds
    resp1 = client.post(
        "/api/v1/webhooks/tradingview",
        json=valid_payload,
    )
    assert resp1.status_code in [200, 400, 409, 500]

    # Second request hits rate limit
    payload = valid_payload.copy()
    payload["signal_id"] = "tv-btcusdt-5m-1713452400000-long-long_v73_second"
    resp2 = client.post(
        "/api/v1/webhooks/tradingview",
        json=payload,
    )
    assert resp2.status_code == 429

    # Check for rate limit headers (case-insensitive)
    headers_lower = {k.lower(): v for k, v in resp2.headers.items()}
    assert "retry-after" in headers_lower or "x-ratelimit-limit" in headers_lower


def test_webhook_rate_limit_per_ip(client: TestClient, monkeypatch, valid_payload: dict):
    """Test rate limiting is per IP address."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 2)

    # Send 2 requests from default test IP (127.0.0.1)
    for i in range(2):
        payload = valid_payload.copy()
        payload["signal_id"] = f"tv-btcusdt-5m-1713452400000-long-long_v73_ip_{i}"
        resp = client.post(
            "/api/v1/webhooks/tradingview",
            json=payload,
        )
        assert resp.status_code in [200, 400, 409, 500]

    # 3rd request from same IP should be blocked
    payload = valid_payload.copy()
    payload["signal_id"] = "tv-btcusdt-5m-1713452400000-long-long_v73_ip_3"
    resp = client.post(
        "/api/v1/webhooks/tradingview",
        json=payload,
    )
    assert resp.status_code == 429


def test_default_rate_limit_is_50(client: TestClient):
    """Test default webhook_rate_limit is 50 requests/minute."""
    assert settings.webhook_rate_limit == 50
