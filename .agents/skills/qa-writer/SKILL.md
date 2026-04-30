---
name: qa-writer
description: "Write or update unit and integration tests for webhook audit, filtering, Telegram, and QA acceptance criteria."
---

# Skill: QA Writer
## Description
Viết unit/integration tests và QA test cases theo `docs/QA_STRATEGY.md` + coverage hiện tại.
Trigger khi user đề cập: viết test QA, audit trail test, failure handling test, news block test, acceptance criteria, QA checklist, integration test.

## Instructions

Đọc `docs/QA_STRATEGY.md`, `docs/QA_COVERAGE_MATRIX.md`, `tests/integration/conftest.py`, và các test hiện có trước khi viết test mới.

---

### Test files hiện có cần ưu tiên mở rộng

```
tests/integration/test_webhook_endpoint.py       # happy path, invalid secret/schema/json, telegram delivery
tests/integration/test_api_regressions.py        # API contract regressions
tests/integration/test_v11_pipeline.py           # V1.1 pipeline behavior
tests/integration/test_signal_repository.py      # repository integration
tests/integration/test_ci_migration_fixture.py   # migration fixture smoke
tests/unit/test_telegram_notifier.py             # Telegram retry/route policy
tests/unit/test_filter_engine.py                 # boolean gate + V1.1 rules
```

Tạo file mới chỉ khi coverage mới không fit vào file hiện có. Nếu tạo mới, dùng fixture/pattern trong `tests/integration/conftest.py`.

### DB setup patterns

QA tests có thể insert data trực tiếp bằng SQLAlchemy Core `insert()` hoặc ORM repository. Dùng model hiện tại, không dùng field cũ.

```python
from datetime import datetime, timezone, timedelta
import uuid
from sqlalchemy import insert

from app.domain.models import MarketEvent, Signal, SignalDecision, WebhookEvent


def insert_market_event(db, minutes_before: int = 5, minutes_after: int = 60) -> str:
    now = datetime.now(timezone.utc)
    event_id = str(uuid.uuid4())
    db.execute(insert(MarketEvent).values(
        id=event_id,
        event_name="FOMC Test",
        start_time=now - timedelta(minutes=minutes_before),
        end_time=now + timedelta(minutes=minutes_after),
        impact="HIGH",
        created_at=now,
    ))
    db.commit()
    return event_id


def insert_existing_signal(db, signal_id: str, side: str = "LONG", timeframe: str = "5m") -> str:
    now = datetime.now(timezone.utc)
    webhook_event_id = str(uuid.uuid4())
    db.execute(insert(WebhookEvent).values(
        id=webhook_event_id,
        received_at=now,
        is_valid_json=True,
        auth_status="OK",
        raw_body={},
    ))

    signal_row_id = str(uuid.uuid4())
    db.execute(insert(Signal).values(
        id=signal_row_id,
        webhook_event_id=webhook_event_id,
        signal_id=signal_id,
        source="test",
        symbol="BTCUSDT",
        timeframe=timeframe,
        side=side,
        price=68000.0,
        entry_price=68000.0,
        stop_loss=67700.0,
        take_profit=68500.0,
        indicator_confidence=0.82,
        created_at=now,
        raw_payload={},
    ))
    db.execute(insert(SignalDecision).values(
        id=str(uuid.uuid4()),
        signal_row_id=signal_row_id,
        decision="PASS_MAIN",
        telegram_route="MAIN",
        created_at=now,
    ))
    db.commit()
    return signal_row_id
```

### Telegram mocking pattern

Current unit tests mostly patch `httpx.AsyncClient` and `asyncio.sleep`; integration tests may patch `TelegramNotifier.send_message`/`notify` depending scope. Keep tests fast by patching sleep.

```python
from unittest.mock import AsyncMock, patch
import httpx
import pytest

@pytest.mark.asyncio
async def test_notify_failure_returns_failed():
    notifier = TelegramNotifier()
    with patch.object(
        notifier,
        "send_message",
        new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
    ):
        status, data, error = await notifier.notify("MAIN", "test")

    assert status == "FAILED"
    assert data is None
    assert "TimeoutException" in error
```

For HTTP retry behavior, follow `tests/unit/test_telegram_notifier.py` mock helpers (`_make_response`, `_make_mock_client`).

### Audit trail verifier

```python
from sqlalchemy import select
from app.domain.models import Signal, SignalDecision, SignalFilterResult, TelegramMessage, WebhookEvent


def verify_full_audit_trail(db, signal_id: str) -> dict:
    signal = db.execute(
        select(Signal).where(Signal.signal_id == signal_id)
    ).scalar_one_or_none()
    assert signal is not None, f"Signal {signal_id} not found"

    webhook_event = db.execute(
        select(WebhookEvent).where(WebhookEvent.id == signal.webhook_event_id)
    ).scalar_one_or_none()
    assert webhook_event is not None, "webhook_event FK broken"

    filter_results = db.execute(
        select(SignalFilterResult).where(SignalFilterResult.signal_row_id == signal.id)
    ).scalars().all()
    assert len(filter_results) >= 3

    decision = db.execute(
        select(SignalDecision).where(SignalDecision.signal_row_id == signal.id)
    ).scalar_one_or_none()
    assert decision is not None

    telegram_messages = db.execute(
        select(TelegramMessage).where(TelegramMessage.signal_row_id == signal.id)
    ).scalars().all()

    return {
        "signal": signal,
        "webhook_event": webhook_event,
        "filter_results": filter_results,
        "decision": decision,
        "telegram_messages": telegram_messages,
    }
```

### Acceptance criteria mapping

| AC | Behavior | Current likely location |
|---|---|---|
| AC-001 | Happy path persists full audit and delivery | `test_webhook_endpoint.py`, `test_api_regressions.py` |
| AC-002 | Invalid secret logs webhook, no signal | `test_webhook_endpoint.py` |
| AC-003 | Duplicate `signal_id` returns `200 DUPLICATE` | `test_webhook_endpoint.py`, `test_api_regressions.py` |
| AC-004 | Telegram fail does not rollback DB | `test_webhook_endpoint.py` or new focused integration |
| AC-005 | Unsupported timeframe logs webhook and rejects | add/keep explicit integration coverage |
| AC-006 | FK audit trail integrity | `test_api_regressions.py`, focused audit test if missing |

### Rules for new QA tests

- Use SQLAlchemy 2.0 `select()`, not `db.query()`.
- Use `datetime.now(timezone.utc)`.
- Generate IDs with `str(uuid.uuid4())`.
- Never assert secrets appear in logs/body.
- Keep Telegram/network mocked; do not call real Telegram.
- If testing background tasks, assert `telegram_messages` row after TestClient response because FastAPI runs background tasks during test response lifecycle.

### Verify

```bash
rtk python -m pytest tests/unit/test_filter_engine.py -v
rtk python -m pytest tests/unit/test_telegram_notifier.py -v
rtk python -m pytest tests/integration/test_webhook_endpoint.py -v
rtk python -m pytest tests/integration/test_api_regressions.py -v
rtk python -m pytest tests/integration/test_v11_pipeline.py -v
```
