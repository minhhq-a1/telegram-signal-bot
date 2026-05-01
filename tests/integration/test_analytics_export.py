from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")


def test_outcome_export_requires_auth(client):
    resp = client.get("/api/v1/analytics/export/outcomes.csv")
    assert resp.status_code == 401


def test_outcome_export_empty_returns_header_only(client):
    resp = client.get("/api/v1/analytics/export/outcomes.csv", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("signal_id,created_at,closed_at")
