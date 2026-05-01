from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")


def test_calibration_report_requires_auth(client):
    resp = client.get("/api/v1/analytics/calibration/report")
    assert resp.status_code == 401


def test_calibration_report_empty_returns_ok(client):
    resp = client.get("/api/v1/analytics/calibration/report", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_health"]["closed_outcomes"] == 0
