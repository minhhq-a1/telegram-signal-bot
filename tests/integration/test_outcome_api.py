from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dashboard-token")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-dashboard-token"}


def test_open_outcome_creates_open_row(client, make_stored_signal):
    signal = make_stored_signal(original_decision="PASS_MAIN")

    resp = client.post(f"/api/v1/signals/{signal.signal_id}/outcome/open", headers=_auth_headers())

    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["signal_row_id"] == signal.id
    assert body["outcome_status"] == "OPEN"


def test_get_outcome_returns_404_when_missing(client, make_stored_signal):
    signal = make_stored_signal(original_decision="PASS_MAIN")

    resp = client.get(f"/api/v1/signals/{signal.signal_id}/outcome", headers=_auth_headers())

    assert resp.status_code == 404


def test_close_outcome_updates_existing_open_row(client, make_stored_signal):
    signal = make_stored_signal(original_decision="PASS_MAIN")
    client.post(f"/api/v1/signals/{signal.signal_id}/outcome/open", headers=_auth_headers())

    resp = client.put(
        f"/api/v1/signals/{signal.signal_id}/outcome",
        headers=_auth_headers(),
        json={
            "exit_price": 74000.0,
            "closed_at": "2026-04-30T10:15:00Z",
            "close_reason": "TP_HIT",
        },
    )

    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["outcome_status"] == "CLOSED"
    assert body["close_reason"] == "TP_HIT"
    assert float(body["exit_price"]) == 74000.0
    assert body["is_win"] is True
    assert round(float(body["pnl_pct"]), 4) == round(((74988.60 - 74000.0) / 74988.60) * 100, 4)
    assert round(float(body["r_multiple"]), 4) == round((74988.60 - 74000.0) / (75429.33 - 74988.60), 4)

def test_close_outcome_invalid_reason_returns_400(client, make_stored_signal):
    signal = make_stored_signal(original_decision="PASS_MAIN")

    resp = client.put(
        f"/api/v1/signals/{signal.signal_id}/outcome",
        headers=_auth_headers(),
        json={
            "exit_price": 74000.0,
            "closed_at": "2026-04-30T10:15:00Z",
            "close_reason": "BAD_REASON",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "INVALID_CLOSE_REASON"


def test_recent_outcomes_requires_auth(client):
    resp = client.get("/api/v1/outcomes/recent")
    assert resp.status_code == 401
