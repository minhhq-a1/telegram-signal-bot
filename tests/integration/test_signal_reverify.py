import pytest
from sqlalchemy import select
from app.domain.models import Signal, SignalReverifyResult  # noqa: F401 — Signal referenced in conftest teardown

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dashboard-token")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-dashboard-token"}


class TestReverifyEndpoint:
    def test_reverify_returns_current_rules_result(self, client, db_session, make_stored_signal):
        """Reverify runs filter engine + strategy validator and returns result."""
        signal = make_stored_signal(
            signal_type="SHORT_SQUEEZE",
            strategy="KELTNER_SQUEEZE",
            squeeze_fired=1,
            mom_direction=-1,
            vol_regime="BREAKOUT_IMMINENT",
            rsi=37.5,
            rsi_slope=-5.7,
            kc_position=0.31,
            atr_pct=0.49,
        )

        resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify", headers=_auth_headers())
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["signal_id"] == signal.signal_id
        assert "reverify_decision" in body
        assert "reverify_score" in body
        assert "reject_code" in body

        # Audit log persisted
        rows = db_session.execute(
            select(SignalReverifyResult).where(SignalReverifyResult.signal_row_id == signal.id)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].reverify_decision == body["reverify_decision"]

    def test_reverify_unknown_signal_returns_404(self, client):
        resp = client.post("/api/v1/signals/does-not-exist/reverify", headers=_auth_headers())
        assert resp.status_code == 404

    def test_reverify_requires_dashboard_auth(self, client, make_stored_signal):
        """No auth → 401."""
        signal = make_stored_signal(signal_type="SHORT_SQUEEZE")
        resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify")
        assert resp.status_code == 401

    def test_reverify_with_valid_auth_returns_200(self, client, db_session, make_stored_signal):
        signal = make_stored_signal(
            signal_type="SHORT_SQUEEZE",
            strategy="KELTNER_SQUEEZE",
            squeeze_fired=1,
            mom_direction=-1,
        )
        # Set all required persisted fields explicitly
        signal.entry_price = 74000.0
        signal.risk_reward = 2.5
        signal.indicator_confidence = 0.82
        db_session.commit()

        resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify", headers=_auth_headers())
        assert resp.status_code == 200

    def test_reverify_uses_db_snapshot_not_raw_payload(self, client, db_session, monkeypatch, make_stored_signal):
        """
        Schema-drift resilience: reverify succeeds even when raw_payload is
        structurally invalid (Finding #2 regression test).
        """
        signal = make_stored_signal(
            signal_type="SHORT_SQUEEZE",
            strategy="KELTNER_SQUEEZE",
            squeeze_fired=1,
            mom_direction=-1,
            vol_regime="BREAKOUT_IMMINENT",
            rsi=37.5,
            rsi_slope=-5.7,
            kc_position=0.31,
            atr_pct=0.49,
        )
        # Overwrite raw_payload with an invalid/legacy shape that would fail
        # TradingViewWebhookPayload validation
        signal.raw_payload = {"garbage": "payload", "invalid": True}
        db_session.commit()

        resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify", headers=_auth_headers())
        # Must NOT fail due to raw_payload schema — uses DB columns instead
        assert resp.status_code == 200, resp.json()
        assert "reverify_decision" in resp.json()

    def test_reverify_missing_required_persisted_fields_returns_422(self, client, db_session, monkeypatch, make_stored_signal):
        """
        Explicit 422 when required persisted replay fields are missing.
        """
        # Create signal with None risk_reward (required field)
        signal = make_stored_signal(
            signal_type="SHORT_SQUEEZExx",  # invalid type to force FAIL, not used
        )
        signal.risk_reward = None
        db_session.commit()

        resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify", headers=_auth_headers())
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["reason"] == "missing_required_persisted_fields"
        assert "risk_reward" in body["detail"]["missing_fields"]
