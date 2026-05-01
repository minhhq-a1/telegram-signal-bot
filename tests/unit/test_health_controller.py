from __future__ import annotations

from app.api.health_controller import _live_payload


def test_live_payload_reports_v12_release_version():
    payload = _live_payload()

    assert payload["status"] == "ok"
    assert payload["service"] == "telegram-signal-bot"
    assert payload["version"] == "1.2.1"
