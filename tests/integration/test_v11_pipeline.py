import json
from pathlib import Path
import pytest

pytestmark = pytest.mark.integration

FIXTURES = Path("docs/examples/v11_sample_payloads")


@pytest.fixture(autouse=True)
def set_webhook_secret(monkeypatch):
    """Set the webhook secret to match the test payload secrets."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "tradingview_shared_secret", "element-camera-fan")


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_short_squeeze_pass_end_to_end(client, db_session):
    resp = client.post("/api/v1/webhooks/tradingview", json=_load("short_squeeze_pass.json"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] in ("PASS_MAIN", "PASS_WARNING"), body


def test_short_squeeze_fail_not_fired(client, db_session):
    resp = client.post(
        "/api/v1/webhooks/tradingview",
        json=_load("short_squeeze_fail_not_fired.json"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "REJECT", body


def test_long_v73_pass(client, db_session):
    resp = client.post("/api/v1/webhooks/tradingview", json=_load("long_v73_pass.json"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] in ("PASS_MAIN", "PASS_WARNING"), body
