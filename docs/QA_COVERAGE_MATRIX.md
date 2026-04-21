# QA Coverage Matrix

Mục tiêu của file này là map acceptance criteria và các case QA quan trọng với test thực tế đang chạy trong repo.

Kết quả verify gần nhất:

```bash
./.venv/bin/python -m pytest -q
```

- `31 passed`

## Acceptance Criteria

| ID | Status | Automated Test | Notes |
|---|---|---|---|
| `AC-001` Happy path end-to-end | `Covered` | `test_webhook_pass_main_logs_telegram_delivery`, `test_get_signal_detail_returns_nested_contract` | Bao phủ persist trước notify, decision, telegram log, signal detail endpoint |
| `AC-002` Auth fail không lưu signal | `Covered` | `test_webhook_invalid_secret_returns_documented_error_contract` | Kiểm tra error contract; audit row được cover bởi invalid secret flow trong integration suite tổng thể |
| `AC-003` Idempotency | `Covered` | `test_webhook_duplicate_returns_valid_duplicate_response` | Có assert `200 DUPLICATE` và response hợp lệ |
| `AC-004` Telegram fail không rollback DB | `Covered` | `test_telegram_total_failure_keeps_audit_and_error_log` | Có assert `delivery_status=FAILED` và `error_log` |
| `AC-005` Unsupported / invalid request boundary | `Partially Covered` | `test_webhook_rejects_invalid_timestamp_format_with_audit_row`, `test_webhook_logs_invalid_json_before_rejecting`, `test_webhook_logs_invalid_schema_before_rejecting` | Invalid payload paths được cover tốt; unsupported timeframe riêng vẫn nên có thêm test explicit |
| `AC-006` Audit trail integrity | `Covered` | `test_get_signal_detail_returns_nested_contract`, `test_webhook_pass_main_logs_telegram_delivery` | Cover linkage qua signal detail và persisted records |

## Sprint 03 Regression Coverage

| Regression | Status | Automated Test |
|---|---|---|
| Telegram logging contract | `Covered` | `test_webhook_pass_main_logs_telegram_delivery` |
| Timestamp validation at API boundary | `Covered` | `test_webhook_rejects_invalid_timestamp_format_with_audit_row` |
| Invalid JSON audit-first | `Covered` | `test_webhook_logs_invalid_json_before_rejecting` |
| Invalid schema audit-first | `Covered` | `test_webhook_logs_invalid_schema_before_rejecting` |
| Signal detail nested contract | `Covered` | `test_get_signal_detail_returns_nested_contract` |
| Seeded DB config matches docs | `Covered` | `test_seeded_signal_bot_config_matches_v1_docs` |
| Duplicate response contract | `Covered` | `test_webhook_duplicate_returns_valid_duplicate_response` |
| Invalid secret error contract | `Covered` | `test_webhook_invalid_secret_returns_documented_error_contract` |
| Cooldown only applies to prior `PASS_MAIN` | `Covered` | `test_cooldown_only_applies_to_prior_pass_main` |
| Telegram total failure keeps audit and error detail | `Covered` | `test_telegram_total_failure_keeps_audit_and_error_log` |

## Unit Coverage

| Area | Status | Automated Test |
|---|---|---|
| Filter engine routing and rejects | `Covered` | [tests/unit/test_filter_engine.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_filter_engine.py:1) |
| Duplicate tolerance boundary | `Covered` | `test_duplicate_tolerance_uses_fractional_0_2_percent_boundary`, `test_duplicate_tolerance_does_not_reject_outside_0_2_percent_boundary` |
| Signal normalization and RR | `Covered` | [tests/unit/test_signal_normalizer.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_signal_normalizer.py:1) |
| Message rendering | `Covered` | [tests/unit/test_message_renderer.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_message_renderer.py:1) |

## Gaps còn nên bổ sung

1. Unsupported timeframe explicit integration test để map thẳng với `AC-005`.
2. News block integration test để map lại với business docs `FILTER_RULES.md`.
3. Một smoke test thủ công/go-live checklist tách riêng khỏi regression suite.
