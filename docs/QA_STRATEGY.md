# QA Strategy — Signal Bot V1.1
<!-- File này là nguồn sự thật chính cho trạng thái QA hiện tại của dự án. -->

## 1. Mục tiêu

Tài liệu này dùng để:
- chốt acceptance criteria trước paper trading
- mô tả test surface thật đang có trong repo
- chỉ rõ lệnh verify chuẩn cho QA và DEV
- phân biệt rõ đâu là tài liệu chiến lược, đâu là hồ sơ lịch sử Sprint

## 2. Trạng thái hiện tại

Kết quả verify gần nhất:

```bash
./.venv/bin/python -m pytest -q
```

- `37 passed`
- không còn regression fail đã biết
- warning `pytest-asyncio` đã được dập bằng `pytest.ini`

Nguồn verify thực thi hiện tại:
- [tests/unit/test_filter_engine.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_filter_engine.py:1)
- [tests/unit/test_signal_normalizer.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_signal_normalizer.py:1)
- [tests/unit/test_message_renderer.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_message_renderer.py:1)
- [tests/integration/test_api_regressions.py](/Users/minhhq/Documents/telegram-signal-bot/tests/integration/test_api_regressions.py:1)

Coverage mapping chi tiết nằm ở:
- [docs/QA_COVERAGE_MATRIX.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_COVERAGE_MATRIX.md:1)

## 3. Test Pyramid

```text
         ┌──────────────┐
         │   E2E / UAT  │  Chưa tự động hóa trong repo hiện tại
         ├──────────────┤
         │  Integration │  API + DB + Telegram mock + audit trail
         ├──────────────┤
         │     Unit     │  Pure logic và formatting
         └──────────────┘
```

### Test layout thực tế

```text
tests/
├── unit/
│   ├── test_filter_engine.py
│   ├── test_signal_normalizer.py
│   └── test_message_renderer.py
└── integration/
    ├── conftest.py
    ├── test_api_regressions.py
    ├── test_webhook_endpoint.py
    └── test_signal_repository.py
```

Ghi chú:
- `tests/integration/test_api_regressions.py` hiện là entrypoint integration chính
- `test_webhook_endpoint.py` và `test_signal_repository.py` là integration bổ sung đang active trong repo
- các file như `test_audit_trail.py`, `test_failure_handling.py`, `test_news_block.py` vẫn là target structure cũ, chưa tách thành file riêng

## 4. Acceptance Criteria — Go/No-Go

Tất cả items sau phải PASS trước khi bật TradingView alert:

### AC-001: Happy path end-to-end

```text
GIVEN valid LONG 5m payload với confidence=0.82
WHEN POST /api/v1/webhooks/tradingview
THEN response 200 PASS_MAIN
AND webhook_events có 1 row
AND signals có 1 row với risk_reward đúng
AND signal_filter_results có >= 5 rows
AND signal_decisions có decision=PASS_MAIN
AND telegram_messages có delivery_status=SENT hoặc FAILED nếu mock
AND GET /api/v1/signals/{signal_id} trả đúng tất cả liên kết trên
```

### AC-002: Auth fail không lưu signal

```text
GIVEN payload với secret sai
WHEN POST webhook
THEN response 401 với error contract đúng docs
AND webhook_events có 1 row với auth_status=INVALID_SECRET
AND signals KHÔNG có row nào
```

### AC-003: Idempotency

```text
GIVEN cùng signal_id gửi 2 lần
WHEN POST lần 2
THEN response 200 DUPLICATE
AND signals vẫn chỉ có 1 row
AND signal_filter_results không tăng thêm
```

### AC-004: Telegram fail không ảnh hưởng audit trail

```text
GIVEN valid signal nhưng Telegram API fail toàn phần
WHEN POST webhook
THEN response 200, không phải 500
AND signal, filter_results, decision vẫn được lưu đầy đủ
AND telegram_messages có delivery_status=FAILED
AND error_log được lưu nếu có nguyên nhân fail
```

### AC-005: Unsupported timeframe

```text
GIVEN payload với timeframe không nằm trong whitelist
WHEN POST webhook
THEN response lỗi đúng contract
AND webhook_events có raw log
```

### AC-006: Audit trail integrity

```text
GIVEN bất kỳ PASS_MAIN signal
WHEN query bằng signal_id
THEN có thể trace: webhook_events -> signals -> signal_filter_results -> signal_decisions -> telegram_messages
AND tất cả FK liên kết đúng
AND không có orphan row
```

## 5. Lệnh verify chuẩn

Full suite:

```bash
./.venv/bin/python -m pytest -q
```

Chỉ unit:

```bash
./.venv/bin/python -m pytest tests/unit -q
```

Chỉ integration:

```bash
./.venv/bin/python -m pytest tests/integration/test_api_regressions.py -q
```

## 6. Tài liệu liên quan

- [docs/QA_COVERAGE_MATRIX.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_COVERAGE_MATRIX.md:1)
- [docs/TEST_CASES.md](/Users/minhhq/Documents/telegram-signal-bot/docs/TEST_CASES.md:1)
- [docs/QA_REVIEW_HISTORY.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_REVIEW_HISTORY.md:1)

## 7. Historical Notes

- [docs/QA_REVIEW_HISTORY.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_REVIEW_HISTORY.md:1) là hồ sơ lịch sử fix/verify QA dùng chung cho các sprint
