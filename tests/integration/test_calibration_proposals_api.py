from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_calibration_proposals_endpoint_returns_proposals(client: TestClient) -> None:
    response = client.get(
        "/api/v1/analytics/calibration/proposals?days=90&min_samples=30",
        headers={"Authorization": "Bearer test-dash-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "period_days" in body
    assert "min_samples" in body
    assert "generated_at" in body
    assert "current_config_version" in body
    assert "proposals" in body
    assert isinstance(body["proposals"], list)


@pytest.mark.integration
def test_calibration_proposals_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/analytics/calibration/proposals")

    assert response.status_code == 401
