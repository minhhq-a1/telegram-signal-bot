# Test Coverage Expansion — Design Spec

**Date:** 2026-04-23  
**Scope:** Issue #9 from code review backlog — bổ sung test coverage cho TelegramNotifier retry/backoff, analytics endpoints, MessageRenderer variants, AuthService

---

## Context

Sau khi merge PR #4 (dead code cleanup + hardening) và PR #7 (PostgreSQL integration tests), các path sau vẫn chưa có test trực tiếp:

| Item | Priority |
|------|----------|
| TelegramNotifier retry + exponential backoff | Trung bình |
| Analytics endpoints `/api/v1/analytics/*` | Trung bình |
| `MessageRenderer.render_warning()` | Thấp |
| `MessageRenderer.render_reject_admin()` | Thấp |
| `AuthService.validate_secret()` | Thấp |

---

## Architecture

### Test tier mapping

| Component | Tier | File |
|-----------|------|------|
| TelegramNotifier | Unit (mocked httpx) | `tests/unit/test_telegram_notifier.py` (new) |
| Analytics endpoints | Integration (SQLite via existing fixtures) | `tests/integration/test_analytics.py` (new) |
| MessageRenderer variants | Unit (pure functions) | `tests/unit/test_message_renderer.py` (extend) |
| AuthService | Unit (mocked settings) | `tests/unit/test_auth_service.py` (new) |

### pytest.ini changes

Add two entries:
- `asyncio_mode = auto` — required for `@pytest.mark.asyncio` on TelegramNotifier async tests
- `markers` block — register `integration` marker (already added on feature/pg-integration-tests, needs to land on main)

---

## Section 1: TelegramNotifier Unit Tests

**File:** `tests/unit/test_telegram_notifier.py`

**Dependencies:** `pytest-asyncio==0.24.0` (already in requirements.txt), `unittest.mock.AsyncMock`

**Mocking strategy:**
- Patch `httpx.AsyncClient.post` to return a mock response or raise exceptions
- Patch `asyncio.sleep` with `AsyncMock` to avoid real delays (7s total across all retries)

**Test cases:**

| Test | What it verifies |
|------|-----------------|
| `test_send_message_success_first_attempt` | HTTP 200 on attempt 1 → returns dict, no sleep called |
| `test_send_message_retries_on_timeout_then_succeeds` | 2x `TimeoutException` then success → `sleep` called twice with 1s, 2s |
| `test_send_message_exhausts_retries_raises` | 4x `TimeoutException` → exception raised after last attempt |
| `test_send_message_retries_on_http_error` | `HTTPStatusError` (e.g. 429) → retries correctly |
| `test_notify_route_none_returns_skipped` | `notify("NONE", ...)` → `("SKIPPED", None, None)` |
| `test_notify_unknown_route_returns_failed` | Unknown route → no chat_id → `("FAILED", None, error_msg)` |
| `test_notify_success_returns_sent_with_message_id` | `send_message` returns `{"result": {"message_id": 123}}` → `("SENT", resp, None)`, `resp["_telegram_message_id"] == "123"` |
| `test_notify_send_fails_returns_failed` | `send_message` raises → `("FAILED", None, error_detail)` |

**Total: 8 test cases**

---

## Section 2: Analytics Integration Tests

**File:** `tests/integration/test_analytics.py`

**Dependencies:** Reuses `client` + `db_session` fixtures from `tests/integration/conftest.py` (SQLite)

**Seeding helpers:** Each test seeds minimal required data via `db_session.add()` + `db_session.commit()` before calling `client.get(...)`. No shared fixtures for seed data — each test is self-contained.

**Test cases:**

| Test | Endpoint | What it verifies |
|------|----------|-----------------|
| `test_summary_empty_db` | `/summary` | All zeros, all required keys present |
| `test_summary_returns_correct_counts` | `/summary` | 2 signals seeded → `total_signals == 2`, decision + telegram counts correct |
| `test_timeline_empty_db` | `/signals/timeline` | `count: 0`, `signals: []` |
| `test_timeline_returns_signals_with_decision` | `/signals/timeline` | Signal + decision seeded → decision field joined correctly |
| `test_timeline_days_param_filters` | `/signals/timeline` | Signal older than `days` → not returned |
| `test_filter_stats_empty_db` | `/filters/stats` | `filter_rules: {}` |
| `test_filter_stats_returns_grouped_by_rule_code` | `/filters/stats` | 2 filter results → grouped by rule_code correctly |
| `test_daily_empty_db` | `/daily` | `daily: {}` |
| `test_daily_returns_correct_day_buckets` | `/daily` | Signals on different dates → correct day keys |
| `test_summary_rejects_days_out_of_range` | `/summary` | `?days=0` → 422, `?days=91` → 422 |

**Total: 10 test cases**

---

## Section 3: MessageRenderer Variants

**File:** `tests/unit/test_message_renderer.py` (extend existing)

**Test cases:**

| Test | What it verifies |
|------|-----------------|
| `test_render_warning_contains_key_info` | Symbol, side, timeframe, reason, confidence, score, signal_id all present |
| `test_render_warning_short_format` | Output shorter than `render_main` — no entry/SL/TP block |
| `test_render_reject_admin_contains_key_info` | Symbol, side, reason, signal_id all present |
| `test_render_reject_admin_minimal` | No confidence/score fields (those belong to warning only) |

**Total: 4 test cases**

---

## Section 4: AuthService Unit Tests

**File:** `tests/unit/test_auth_service.py` (new)

**Mocking strategy:** `monkeypatch.setattr(settings, "tradingview_shared_secret", "correct-secret")` to control the expected secret without importing real config.

**Test cases:**

| Test | Input | Expected |
|------|-------|----------|
| `test_validate_secret_correct` | `"correct-secret"` | `True` |
| `test_validate_secret_wrong` | `"wrong-secret"` | `False` |
| `test_validate_secret_none` | `None` | `False` |
| `test_validate_secret_empty_string` | `""` | `False` |

**Total: 4 test cases**

---

## Summary

| File | Status | Test count |
|------|--------|-----------|
| `pytest.ini` | Modify | — |
| `tests/unit/test_telegram_notifier.py` | New | 8 |
| `tests/integration/test_analytics.py` | New | 10 |
| `tests/unit/test_message_renderer.py` | Extend | +4 |
| `tests/unit/test_auth_service.py` | New | 4 |
| **Total** | | **26** |

All 26 new tests must pass locally before creating a PR. No new dependencies required.
