"""Integration tests for webhook rate limiting."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings


def test_default_rate_limit_is_50():
    """Default webhook_rate_limit is 50 requests/minute."""
    assert settings.webhook_rate_limit == 50


def test_requests_below_limit_pass(client: TestClient, valid_payload: dict, monkeypatch):
    """Requests within rate limit are processed normally."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 5)

    for i in range(5):
        payload = dict(valid_payload, signal_id=f"rate-limit-pass-{i}")
        resp = client.post("/api/v1/webhooks/tradingview", json=payload)
        assert resp.status_code != 429, f"Request {i + 1} should not be rate limited"


def test_request_exceeding_limit_returns_429(client: TestClient, valid_payload: dict, monkeypatch):
    """Request beyond rate limit returns 429 with Retry-After header."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 3)

    for i in range(3):
        payload = dict(valid_payload, signal_id=f"rate-limit-block-{i}")
        client.post("/api/v1/webhooks/tradingview", json=payload)

    payload = dict(valid_payload, signal_id="rate-limit-block-over")
    resp = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert resp.status_code == 429

    headers_lower = {k.lower(): v for k, v in resp.headers.items()}
    assert "retry-after" in headers_lower, "429 response must include Retry-After header"


def test_rate_limit_is_per_ip(client: TestClient, valid_payload: dict, monkeypatch):
    """Rate limit counter is isolated per IP address."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 2)

    for i in range(2):
        payload = dict(valid_payload, signal_id=f"rate-limit-ip-{i}")
        resp = client.post("/api/v1/webhooks/tradingview", json=payload)
        assert resp.status_code != 429

    payload = dict(valid_payload, signal_id="rate-limit-ip-over")
    resp = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert resp.status_code == 429
