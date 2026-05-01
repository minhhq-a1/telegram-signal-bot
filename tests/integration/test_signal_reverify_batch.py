from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dashboard-token")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-dashboard-token"}


def test_batch_reverify_requires_auth(client):
    resp = client.post("/api/v1/signals/reverify/batch", json={})
    assert resp.status_code == 401


def test_batch_reverify_enforces_limit(client):
    resp = client.post(
        "/api/v1/signals/reverify/batch",
        headers=_auth_headers(),
        json={"limit": 1001},
    )
    assert resp.status_code == 400


def test_batch_reverify_returns_results(client, make_stored_signal):
    sig1 = make_stored_signal(signal_type="SHORT_SQUEEZE", strategy="KELTNER_SQUEEZE")
    sig2 = make_stored_signal(signal_type="SHORT_SQUEEZE", strategy="KELTNER_SQUEEZE")

    resp = client.post(
        "/api/v1/signals/reverify/batch",
        headers=_auth_headers(),
        json={
            "days": 30,
            "limit": 10,
            "decision": ["PASS_MAIN"],
            "signal_type": ["SHORT_SQUEEZE"],
            "persist_results": True,
        },
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["processed"] >= 2
    ids = {row["signal_id"] for row in body["results"]}
    assert sig1.signal_id in ids
    assert sig2.signal_id in ids
