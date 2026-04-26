"""T1: Dashboard and analytics auth surface tests."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from app.core.config import settings

ANALYTICS_URLS = [
    "/api/v1/analytics/summary",
    "/api/v1/analytics/signals/timeline",
    "/api/v1/analytics/filters/stats",
    "/api/v1/analytics/daily",
]

@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    monkeypatch.setattr(settings, "dashboard_token", "test-dash-token")

def test_dashboard_no_token_returns_401(client: TestClient):
    assert client.get("/dashboard", follow_redirects=False).status_code == 401

def test_dashboard_wrong_token_returns_401(client: TestClient):
    assert client.get("/dashboard", headers={"Authorization": "Bearer wrong"}, follow_redirects=False).status_code == 401

def test_dashboard_correct_token_returns_html(client: TestClient):
    resp = client.get("/dashboard", headers={"Authorization": "Bearer test-dash-token"}, follow_redirects=False)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

def test_dashboard_html_contains_injected_token(client: TestClient):
    resp = client.get("/dashboard", headers={"Authorization": "Bearer test-dash-token"}, follow_redirects=False)
    assert "window.__TOKEN__ = " in resp.text
    assert "test-dash-token" in resp.text

def test_dashboard_token_injection_safe_with_special_chars(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "dashboard_token", 'tok"en</script><script>alert(1)')
    resp = client.get("/dashboard", headers={"Authorization": 'Bearer tok"en</script><script>alert(1)'}, follow_redirects=False)
    assert resp.status_code == 200
    assert "</script><script>" not in resp.text  # not injected raw into HTML

def test_dashboard_html_not_directly_accessible(client: TestClient):
    assert client.get("/static/dashboard.html").status_code == 404

@pytest.mark.parametrize("url", ANALYTICS_URLS)
def test_analytics_no_token_returns_401(client: TestClient, url):
    assert client.get(url).status_code == 401

@pytest.mark.parametrize("url", ANALYTICS_URLS)
def test_analytics_correct_token_returns_200(client: TestClient, url):
    assert client.get(url, headers={"Authorization": "Bearer test-dash-token"}).status_code == 200

def test_signal_detail_no_token_returns_401(client: TestClient):
    assert client.get("/api/v1/signals/nonexistent").status_code == 401

def test_signal_detail_correct_token_passes_auth(client: TestClient):
    resp = client.get("/api/v1/signals/nonexistent", headers={"Authorization": "Bearer test-dash-token"})
    assert resp.status_code == 404  # auth passed, signal not found

def test_open_access_when_no_token_configured_in_dev(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "dashboard_token", None)
    monkeypatch.setattr(settings, "app_env", "dev")
    assert client.get("/api/v1/analytics/summary").status_code == 200


def test_dashboard_fail_closed_when_no_token_configured_in_prod_alias(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "dashboard_token", None)
    monkeypatch.setattr(settings, "app_env", "prod")
    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Dashboard auth misconfigured"


def test_dashboard_fail_closed_when_no_token_configured_in_production(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "dashboard_token", None)
    monkeypatch.setattr(settings, "app_env", "production")
    resp = client.get("/api/v1/signals/nonexistent")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Dashboard auth misconfigured"
