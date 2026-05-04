from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.repositories.config_repo import ConfigRepository


@pytest.mark.integration
def test_dry_run_returns_changed_paths(client: TestClient, db: Session, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/admin/config/signal-bot/dry-run",
        json={"config_value": {"confidence_thresholds": {"5m": 0.81}}, "change_reason": "Raise 5m threshold after calibration review"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert "changed_paths" in body
    assert "confidence_thresholds.5m" in body["changed_paths"]
    assert body["config_value"]["confidence_thresholds"]["5m"] == 0.81


@pytest.mark.integration
def test_dry_run_does_not_mutate_config(client: TestClient, db: Session, auth_headers: dict) -> None:
    _, version_before = ConfigRepository(db).get_signal_bot_config_with_version()

    client.post(
        "/api/v1/admin/config/signal-bot/dry-run",
        json={"config_value": {"confidence_thresholds": {"5m": 0.99}}, "change_reason": "Test dry-run does not persist"},
        headers=auth_headers,
    )

    _, version_after = ConfigRepository(db).get_signal_bot_config_with_version()
    assert version_after == version_before


@pytest.mark.integration
def test_dry_run_rejects_short_reason(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/admin/config/signal-bot/dry-run",
        json={"config_value": {"confidence_thresholds": {"5m": 0.81}}, "change_reason": "short"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "CONFIG_REASON_REQUIRED"


@pytest.mark.integration
def test_dry_run_rejects_invalid_config(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/admin/config/signal-bot/dry-run",
        json={"config_value": {"confidence_thresholds": {"5m": 1.5}}, "change_reason": "Invalid threshold over 1.0"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "CONFIG_VALIDATION_FAILED"


@pytest.mark.integration
def test_rollback_restores_previous_config(client: TestClient, db: Session, auth_headers: dict) -> None:
    config_before, version_before = ConfigRepository(db).get_signal_bot_config_with_version()

    # Apply a change
    client.put(
        "/api/v1/admin/config/signal-bot",
        json={"config_value": {"confidence_thresholds": {"5m": 0.88}}, "change_reason": "Test change for rollback"},
        headers=auth_headers,
    )

    _, version_after_change = ConfigRepository(db).get_signal_bot_config_with_version()
    assert version_after_change == version_before + 1

    # Rollback
    response = client.post(
        "/api/v1/admin/config/signal-bot/rollback",
        json={"target_version": version_before, "change_reason": "Rollback test change"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target_version"] == version_before
    assert body["new_version"] == version_before + 2

    config_after_rollback, _ = ConfigRepository(db).get_signal_bot_config_with_version()
    assert config_after_rollback["confidence_thresholds"]["5m"] == config_before["confidence_thresholds"]["5m"]


@pytest.mark.integration
def test_rollback_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/admin/config/signal-bot/rollback",
        json={"target_version": 1, "change_reason": "Test rollback without auth"},
    )

    assert response.status_code == 401
