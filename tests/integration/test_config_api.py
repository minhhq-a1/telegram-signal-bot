from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dashboard-token")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-dashboard-token"}


def test_get_signal_bot_config_requires_auth(client):
    resp = client.get("/api/v1/admin/config/signal-bot")
    assert resp.status_code == 401


def test_get_signal_bot_config_returns_version_and_payload(client):
    resp = client.get("/api/v1/admin/config/signal-bot", headers=_auth_headers())
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["config_key"] == "signal_bot_config"
    assert "version" in body
    assert "config_value" in body


def test_put_signal_bot_config_requires_change_reason(client):
    resp = client.put(
        "/api/v1/admin/config/signal-bot",
        headers=_auth_headers(),
        json={"config_value": {"confidence_thresholds": {"5m": 0.80}}, "change_reason": "short"},
    )
    assert resp.status_code == 400


def test_put_signal_bot_config_updates_and_writes_audit_log(client):
    resp = client.put(
        "/api/v1/admin/config/signal-bot",
        headers=_auth_headers(),
        json={
            "config_value": {"confidence_thresholds": {"5m": 0.80}},
            "change_reason": "Raise 5m threshold after calibration review",
        },
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["version"] >= 1
    assert body["config_value"]["confidence_thresholds"]["5m"] == 0.80

    audit_resp = client.get("/api/v1/admin/config/audit-log", headers=_auth_headers())
    assert audit_resp.status_code == 200, audit_resp.json()
    assert audit_resp.json()["count"] >= 1
