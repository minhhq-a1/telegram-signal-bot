"""Unit tests for AuthService.validate_secret."""
from __future__ import annotations

import pytest

from app.services.auth_service import AuthService
from app.core.config import settings


def test_validate_secret_correct(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_shared_secret", "correct-secret")
    assert AuthService.validate_secret("correct-secret") is True


def test_validate_secret_wrong(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_shared_secret", "correct-secret")
    assert AuthService.validate_secret("wrong-secret") is False


def test_validate_secret_none(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_shared_secret", "correct-secret")
    assert AuthService.validate_secret(None) is False


def test_validate_secret_empty_string(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_shared_secret", "correct-secret")
    assert AuthService.validate_secret("") is False
