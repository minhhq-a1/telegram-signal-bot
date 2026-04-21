# Skill: QA Writer
## Description
Viết integration tests và QA test cases theo `docs/QA_STRATEGY.md`.
Trigger khi user đề cập: viết test QA, TC-017 đến TC-023, audit trail test, failure handling test, news block test, acceptance criteria, QA checklist, integration test.

## Instructions

Đọc `docs/QA_STRATEGY.md` trước khi viết bất kỳ test nào.

---

### Test files cần tạo

```
tests/integration/
├── test_audit_trail.py      ← TC-021: FK integrity end-to-end
├── test_failure_handling.py ← TC-017, TC-018: invalid secret log, Telegram fail
└── test_news_block.py       ← TC-019: market_events integration
tests/unit/
└── test_telegram_notifier.py ← TC-014 + retry patterns từ skill telegram-notifier
```

### Pattern: setup DB data trực tiếp

QA tests cần insert data phức tạp (market_events, existing signals) trực tiếp vào DB — không đi qua API:

```python
from sqlalchemy import insert
from datetime import datetime, timezone, timedelta
import uuid

def insert_market_event(db, minutes_before=5, minutes_after=60):
    now = datetime.now(timezone.utc)
    db.execute(insert(MarketEvent).values(
        id=str(uuid.uuid4()),
        event_name="FOMC Test",
        event_category="FOMC",
        start_time=now - timedelta(minutes=minutes_before),
        end_time=now + timedelta(minutes=minutes_after),
        impact_level="HIGH",
        is_active=True,
        created_at=now,
    ))
    db.commit()

def insert_existing_signal(db, signal_id, side="LONG", timeframe="5m"):
    """Insert PASS_MAIN signal để test cooldown/duplicate."""
    now = datetime.now(timezone.utc)
    we_id = str(uuid.uuid4())
    db.execute(insert(WebhookEvent).values(
        id=we_id, received_at=now, is_valid_json=True,
        auth_status="OK", raw_body={}
    ))
    sig_id = str(uuid.uuid4())
    db.execute(insert(Signal).values(
        id=sig_id, webhook_event_id=we_id, signal_id=signal_id,
        source="test", symbol="BTCUSDT", timeframe=timeframe,
        side=side, price=68000.0, entry_price=68000.0,
        stop_loss=67700.0, take_profit=68500.0,
        indicator_confidence=0.82, created_at=now,
        raw_payload={}
    ))
    db.execute(insert(SignalDecision).values(
        id=str(uuid.uuid4()), signal_row_id=sig_id,
        decision="PASS_MAIN", telegram_route="MAIN", created_at=now
    ))
    db.commit()
    return sig_id
```

### Pattern: mock Telegram với respx

```python
import respx
import httpx
import re

TELEGRAM_URL_PATTERN = re.compile(r"https://api\.telegram\.org/.*")

@respx.mock
def test_with_telegram_mock(client, db):
    # Success mock
    respx.post(TELEGRAM_URL_PATTERN).mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )
    # ... test body

@respx.mock
def test_with_telegram_fail(client, db):
    # Fail mock — tất cả requests đều timeout
    respx.post(TELEGRAM_URL_PATTERN).mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    # ... test body
```

### Pattern: verify audit trail

```python
from sqlalchemy import select

def verify_full_audit_trail(db, signal_id: str) -> dict:
    """Verify và trả về toàn bộ audit trail của 1 signal."""
    signal = db.execute(
        select(Signal).where(Signal.signal_id == signal_id)
    ).scalar_one_or_none()
    assert signal is not None, f"Signal {signal_id} not found"

    webhook_event = db.execute(
        select(WebhookEvent).where(WebhookEvent.id == signal.webhook_event_id)
    ).scalar_one_or_none()
    assert webhook_event is not None, "webhook_event FK broken"

    filter_results = db.execute(
        select(SignalFilterResult).where(
            SignalFilterResult.signal_row_id == signal.id
        )
    ).scalars().all()
    assert len(filter_results) >= 3, f"Too few filter results: {len(filter_results)}"

    decision = db.execute(
        select(SignalDecision).where(SignalDecision.signal_row_id == signal.id)
    ).scalar_one_or_none()
    assert decision is not None, "decision FK broken"

    return {
        "signal": signal,
        "webhook_event": webhook_event,
        "filter_results": filter_results,
        "decision": decision,
    }
```

### Acceptance criteria mapping

Mỗi test phải map tới AC trong QA_STRATEGY.md:

| Test | AC |
|---|---|
| `test_happy_path_full_audit_trail` | AC-001 |
| `test_invalid_secret_still_logs_webhook` | AC-002 |
| `test_duplicate_signal_id_idempotent` | AC-003 |
| `test_telegram_fail_does_not_rollback` | AC-004 |
| `test_unsupported_timeframe_logs_webhook` | AC-005 |
| `test_audit_trail_fk_integrity` | AC-006 |

### Verify

```bash
python -m pytest tests/integration/test_audit_trail.py -v -m integration
python -m pytest tests/integration/test_failure_handling.py -v -m integration
python -m pytest tests/integration/test_news_block.py -v -m integration

# Tất cả AC-001 → AC-006 phải pass trước go-live
```
