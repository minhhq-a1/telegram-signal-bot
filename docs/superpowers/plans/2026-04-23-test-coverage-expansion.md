# Test Coverage Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 26 unit and integration tests covering TelegramNotifier retry/backoff, analytics endpoints, MessageRenderer variants, and AuthService.

**Architecture:** Unit tests mock external dependencies (httpx, settings); integration tests reuse the existing `client` + `db_session` SQLite fixtures from `tests/integration/conftest.py`. A root `tests/conftest.py` is added first to ensure env vars are set before any app module is imported, unblocking unit tests that depend on `settings`.

**Tech Stack:** Python 3.12, pytest 8.3.3, pytest-asyncio 0.24.0, unittest.mock, httpx 0.27.2, SQLAlchemy 2.0, FastAPI TestClient

> **Running tests:** Use the project venv — `VENV=/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python` and run as `$VENV -m pytest <args> --rootdir=/Users/minhhq/Documents/telegram-signal-bot`

---

## File Map

| File | Action | Notes |
|------|--------|-------|
| `pytest.ini` | Modify | Add `asyncio_mode = auto` + `markers` block |
| `tests/conftest.py` | Create | Root env var setup, required for unit tests importing `settings` |
| `tests/unit/test_telegram_notifier.py` | Create | 8 async unit tests for retry + notify |
| `tests/integration/test_analytics.py` | Create | 10 integration tests for 4 analytics endpoints |
| `tests/unit/test_message_renderer.py` | Extend | Add 4 tests for `render_warning` + `render_reject_admin` |
| `tests/unit/test_auth_service.py` | Create | 4 unit tests for `validate_secret` |

---

### Task T1: pytest.ini + root conftest — async mode + env var bootstrap

**Files:**
- Modify: `pytest.ini`
- Create: `tests/conftest.py`

- [ ] **Step 1: Update pytest.ini**

Replace the contents of `pytest.ini` with:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
markers =
    integration: marks tests as requiring a live PostgreSQL database
```

- [ ] **Step 2: Create tests/conftest.py**

```python
"""Root conftest: set required env vars before any app module is imported."""
from __future__ import annotations
import os

os.environ.setdefault("tradingview_shared_secret", "test-secret")
os.environ.setdefault("database_url", "sqlite:///./test_bootstrap.db")
os.environ.setdefault("telegram_bot_token", "test-token")
os.environ.setdefault("telegram_main_chat_id", "main-chat")
os.environ.setdefault("telegram_warn_chat_id", "warn-chat")
os.environ.setdefault("telegram_admin_chat_id", "admin-chat")
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

```bash
pytest tests/unit -v
```

Expected: all existing unit tests pass (currently 6 tests).

- [ ] **Step 4: Commit**

```bash
git add pytest.ini tests/conftest.py
git commit -m "chore: add asyncio_mode=auto, integration marker, root env conftest"
```

---

### Task T2: TelegramNotifier unit tests — send_message retry behavior

**Files:**
- Create: `tests/unit/test_telegram_notifier.py`

- [ ] **Step 1: Create the test file with send_message tests**

```python
"""Unit tests for TelegramNotifier.send_message retry + exponential backoff."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest

from app.services.telegram_notifier import TelegramNotifier


def _make_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"ok": True, "result": {"message_id": 1}}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


async def test_send_message_success_first_attempt():
    notifier = TelegramNotifier()
    mock_resp = _make_response(200, {"ok": True, "result": {"message_id": 42}})

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await notifier.send_message("chat-123", "hello")

    assert result == {"ok": True, "result": {"message_id": 42}}
    mock_sleep.assert_not_called()


async def test_send_message_retries_on_timeout_then_succeeds():
    notifier = TelegramNotifier()
    success_resp = _make_response(200, {"ok": True, "result": {"message_id": 99}})

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[
            httpx.TimeoutException("timeout"),
            httpx.TimeoutException("timeout"),
            success_resp,
        ])
        mock_client_cls.return_value = mock_client

        result = await notifier.send_message("chat-123", "hello")

    assert result == {"ok": True, "result": {"message_id": 99}}
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2**0
    mock_sleep.assert_any_call(2)  # 2**1


async def test_send_message_exhausts_retries_raises():
    notifier = TelegramNotifier()

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("always timeout")
        )
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.TimeoutException):
            await notifier.send_message("chat-123", "hello")

    # 4 attempts = 3 sleeps (no sleep after last attempt)
    assert mock_sleep.call_count == 3
    mock_sleep.assert_any_call(1)   # 2**0
    mock_sleep.assert_any_call(2)   # 2**1
    mock_sleep.assert_any_call(4)   # 2**2


async def test_send_message_retries_on_http_status_error():
    notifier = TelegramNotifier()
    success_resp = _make_response(200, {"ok": True, "result": {"message_id": 7}})
    error_resp = _make_response(429)

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[error_resp, success_resp])
        mock_client_cls.return_value = mock_client

        result = await notifier.send_message("chat-123", "hello")

    assert result["result"]["message_id"] == 7
```

- [ ] **Step 2: Run to verify tests pass**

```bash
pytest tests/unit/test_telegram_notifier.py -v
```

Expected: 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_telegram_notifier.py
git commit -m "test: add TelegramNotifier send_message retry unit tests"
```

---

### Task T3: TelegramNotifier unit tests — notify routing

**Files:**
- Modify: `tests/unit/test_telegram_notifier.py`

- [ ] **Step 1: Append notify tests to the file**

Add these 4 tests after the existing tests in `tests/unit/test_telegram_notifier.py`:

```python
async def test_notify_route_none_returns_skipped():
    notifier = TelegramNotifier()
    status, resp, err = await notifier.notify("NONE", "any text")
    assert status == "SKIPPED"
    assert resp is None
    assert err is None


async def test_notify_unknown_route_returns_failed():
    notifier = TelegramNotifier()
    status, resp, err = await notifier.notify("INVALID_ROUTE", "any text")
    assert status == "FAILED"
    assert resp is None
    assert err is not None
    assert "INVALID_ROUTE" in err


async def test_notify_success_returns_sent_with_message_id():
    notifier = TelegramNotifier()
    fake_api_response = {"ok": True, "result": {"message_id": 123}}

    with patch.object(notifier, "send_message", new=AsyncMock(return_value=fake_api_response)):
        status, resp, err = await notifier.notify("MAIN", "hello main")

    assert status == "SENT"
    assert err is None
    assert resp is not None
    assert resp["_telegram_message_id"] == "123"


async def test_notify_send_fails_returns_failed():
    notifier = TelegramNotifier()

    with patch.object(
        notifier,
        "send_message",
        new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
    ):
        status, resp, err = await notifier.notify("MAIN", "hello")

    assert status == "FAILED"
    assert resp is None
    assert err is not None
    assert "TimeoutException" in err
```

- [ ] **Step 2: Run all TelegramNotifier tests**

```bash
pytest tests/unit/test_telegram_notifier.py -v
```

Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_telegram_notifier.py
git commit -m "test: add TelegramNotifier notify routing unit tests"
```

---

### Task T4: Analytics integration tests — empty DB + summary counts

**Files:**
- Create: `tests/integration/test_analytics.py`

- [ ] **Step 1: Create test file with empty DB and summary count tests**

```python
"""Integration tests for /api/v1/analytics/* endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import AuthStatus, DecisionType, DeliveryStatus, RuleResult, RuleSeverity, TelegramRoute
from app.domain.models import Signal, SignalDecision, SignalFilterResult, TelegramMessage, WebhookEvent


def _make_webhook(db_session: Session) -> WebhookEvent:
    wh = WebhookEvent(
        id=str(uuid.uuid4()),
        raw_body={},
        auth_status=AuthStatus.OK,
    )
    db_session.add(wh)
    db_session.flush()
    return wh


def _make_signal(db_session: Session, webhook: WebhookEvent, signal_id: str | None = None, created_at: datetime | None = None) -> Signal:
    sig = Signal(
        id=str(uuid.uuid4()),
        webhook_event_id=webhook.id,
        signal_id=signal_id or str(uuid.uuid4()),
        source="Bot_Webhook_v84",
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        price=68000.0,
        entry_price=68000.0,
        stop_loss=67500.0,
        take_profit=69000.0,
        risk_reward=2.0,
        indicator_confidence=0.82,
        raw_payload={},
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(sig)
    db_session.flush()
    return sig


def test_summary_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 0
    assert data["decisions"] == {}
    assert data["telegram_delivery"] == {}
    assert data["by_side"] == {}
    assert data["by_symbol"] == {}
    assert data["by_timeframe"] == {}
    assert data["by_strategy"] == {}
    assert data["avg_confidence"] == 0.0
    assert data["avg_server_score"] == 0.0


def test_summary_returns_correct_counts(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    sig1 = _make_signal(db_session, wh)
    sig2 = _make_signal(db_session, wh)

    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig1.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="ok",
        telegram_route=TelegramRoute.MAIN,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.add(TelegramMessage(
        id=str(uuid.uuid4()),
        signal_row_id=sig1.id,
        chat_id="main-chat",
        route=TelegramRoute.MAIN,
        message_text="msg",
        delivery_status=DeliveryStatus.SENT,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_signals"] == 2
    assert data["decisions"].get("PASS_MAIN") == 1
    assert data["telegram_delivery"].get("SENT") == 1


def test_summary_rejects_days_out_of_range(client: TestClient):
    assert client.get("/api/v1/analytics/summary?days=0").status_code == 422
    assert client.get("/api/v1/analytics/summary?days=91").status_code == 422
```

- [ ] **Step 2: Run to verify these tests pass**

```bash
pytest tests/integration/test_analytics.py::test_summary_empty_db tests/integration/test_analytics.py::test_summary_returns_correct_counts tests/integration/test_analytics.py::test_summary_rejects_days_out_of_range -v
```

Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_analytics.py
git commit -m "test: add analytics summary endpoint integration tests"
```

---

### Task T5: Analytics integration tests — timeline, filter stats, daily

**Files:**
- Modify: `tests/integration/test_analytics.py`

- [ ] **Step 1: Append timeline, filter stats, and daily tests**

Add these tests to the end of `tests/integration/test_analytics.py`:

```python
def test_timeline_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/signals/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["signals"] == []


def test_timeline_returns_signals_with_decision(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    sig = _make_signal(db_session, wh, signal_id="timeline-sig-001")
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="ok",
        telegram_route=TelegramRoute.MAIN,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/signals/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["signals"][0]["signal_id"] == "timeline-sig-001"
    assert data["signals"][0]["decision"] == "PASS_MAIN"


def test_timeline_days_param_filters(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    old_time = datetime.now(timezone.utc) - timedelta(days=10)
    _make_signal(db_session, wh, signal_id="old-signal", created_at=old_time)
    db_session.commit()

    resp = client.get("/api/v1/analytics/signals/timeline?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


def test_filter_stats_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/filters/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["filter_rules"] == {}


def test_filter_stats_returns_grouped_by_rule_code(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    sig = _make_signal(db_session, wh)
    now = datetime.now(timezone.utc)
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code="SYMBOL_ALLOWED",
        rule_group="validation",
        result=RuleResult.PASS,
        severity=RuleSeverity.INFO,
        score_delta=0.0,
        details={},
        created_at=now,
    ))
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code="SYMBOL_ALLOWED",
        rule_group="validation",
        result=RuleResult.FAIL,
        severity=RuleSeverity.INFO,
        score_delta=0.0,
        details={},
        created_at=now,
    ))
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code="CONFIDENCE_CHECK",
        rule_group="quality",
        result=RuleResult.PASS,
        severity=RuleSeverity.INFO,
        score_delta=0.0,
        details={},
        created_at=now,
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/filters/stats")
    assert resp.status_code == 200
    data = resp.json()
    rules = data["filter_rules"]
    assert rules["SYMBOL_ALLOWED"]["PASS"] == 1
    assert rules["SYMBOL_ALLOWED"]["FAIL"] == 1
    assert rules["CONFIDENCE_CHECK"]["PASS"] == 1


def test_daily_empty_db(client: TestClient):
    resp = client.get("/api/v1/analytics/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert data["daily"] == {}


def test_daily_returns_correct_day_buckets(client: TestClient, db_session: Session):
    wh = _make_webhook(db_session)
    day1 = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    sig1 = _make_signal(db_session, wh, signal_id="day1-sig", created_at=day1)
    sig2 = _make_signal(db_session, wh, signal_id="day2-sig", created_at=day2)
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig1.id,
        decision=DecisionType.PASS_MAIN,
        decision_reason="ok",
        telegram_route=TelegramRoute.MAIN,
        created_at=day1,
    ))
    db_session.add(SignalDecision(
        id=str(uuid.uuid4()),
        signal_row_id=sig2.id,
        decision=DecisionType.REJECT,
        decision_reason="filtered",
        telegram_route=TelegramRoute.NONE,
        created_at=day2,
    ))
    db_session.commit()

    resp = client.get("/api/v1/analytics/daily?days=30")
    assert resp.status_code == 200
    data = resp.json()
    daily = data["daily"]
    assert "2026-04-20" in daily
    assert "2026-04-21" in daily
    assert daily["2026-04-20"]["PASS_MAIN"] == 1
    assert daily["2026-04-21"]["REJECT"] == 1
```

- [ ] **Step 2: Run all analytics tests**

```bash
pytest tests/integration/test_analytics.py -v
```

Expected: 10 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_analytics.py
git commit -m "test: add analytics timeline, filter stats, and daily endpoint tests"
```

---

### Task T6: MessageRenderer variant tests

**Files:**
- Modify: `tests/unit/test_message_renderer.py`

- [ ] **Step 1: Append 4 tests to the existing file**

Add these tests to the end of `tests/unit/test_message_renderer.py`:

```python
def test_render_warning_contains_key_info():
    signal = {
        "side": "SHORT",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "signal_id": "warn-signal-001",
        "risk_reward": 1.6,
        "indicator_confidence": 0.74,
        "regime": "RANGING",
        "vol_regime": "HIGH_VOL",
    }
    text = MessageRenderer.render_warning(signal, 0.71, "Low confidence")
    assert "ETHUSDT" in text
    assert "SHORT" in text
    assert "15m" in text
    assert "Low confidence" in text
    assert "74%" in text   # confidence
    assert "71%" in text   # score
    assert "warn-signal-001" in text


def test_render_warning_no_entry_sl_tp_block():
    signal = {
        "side": "LONG",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "signal_id": "warn-signal-002",
        "risk_reward": None,
        "indicator_confidence": 0.70,
        "regime": None,
        "vol_regime": None,
    }
    text = MessageRenderer.render_warning(signal, 0.65, "Weak trend")
    assert "Entry:" not in text
    assert "SL:" not in text
    assert "TP:" not in text


def test_render_reject_admin_contains_key_info():
    signal = {
        "side": "LONG",
        "symbol": "SOLUSDT",
        "timeframe": "1h",
        "signal_id": "reject-signal-001",
    }
    text = MessageRenderer.render_reject_admin(signal, "Below confidence threshold")
    assert "SOLUSDT" in text
    assert "LONG" in text
    assert "1h" in text
    assert "Below confidence threshold" in text
    assert "reject-signal-001" in text


def test_render_reject_admin_has_no_confidence_or_score():
    signal = {
        "side": "SHORT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "signal_id": "reject-signal-002",
    }
    text = MessageRenderer.render_reject_admin(signal, "Cooldown active")
    assert "Conf:" not in text
    assert "Score:" not in text
```

- [ ] **Step 2: Run message renderer tests**

```bash
pytest tests/unit/test_message_renderer.py -v
```

Expected: 6 tests pass (2 existing + 4 new).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_message_renderer.py
git commit -m "test: add render_warning and render_reject_admin unit tests"
```

---

### Task T7: AuthService unit tests

**Files:**
- Create: `tests/unit/test_auth_service.py`

- [ ] **Step 1: Create the test file**

```python
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
```

- [ ] **Step 2: Run auth service tests**

```bash
pytest tests/unit/test_auth_service.py -v
```

Expected: 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_auth_service.py
git commit -m "test: add AuthService.validate_secret unit tests"
```

---

### Task T8: Full test run + verification

**Files:** None (verification only)

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/unit -v
```

Expected: 43 unit tests pass — 27 existing tests (filter_engine x17, logging x2, message_renderer x2, signal_normalizer x6) plus new TelegramNotifier (8), MessageRenderer variants (4), and AuthService (4) tests.

- [ ] **Step 2: Run all integration tests**

```bash
pytest tests/integration -v
```

Expected: integration tests run (SQLite, no PostgreSQL needed). All pass.

- [ ] **Step 3: Run full suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass (no failures, integration tests not skipped since SQLite conftest is active).

- [ ] **Step 4: Commit if any fixes needed, then invoke finishing-a-development-branch**

If all green, invoke the `superpowers:finishing-a-development-branch` skill to wrap up the branch and create a PR.
