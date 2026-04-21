# Sprint 1-2 Fix Checklist

Mục tiêu của file này là gom các findings QA hiện tại thành checklist sửa lỗi theo thứ tự unblock thực tế cho DEV.

Phạm vi:
- Sửa để app boot được
- Sửa để `POST /api/v1/webhooks/tradingview` chạy được happy path
- Sửa để contract request/response khớp docs
- Sửa để audit trail và DB config đúng nguyên tắc dự án
- Bổ sung test tối thiểu để khóa regression

## Definition Of Done Cho Sprint Fix

- App boot được với cấu hình hợp lệ
- `POST /api/v1/webhooks/tradingview` nhận được payload đúng theo docs hiện tại
- Happy path không crash và commit đầy đủ:
  - `webhook_events`
  - `signals`
  - `signal_filter_results`
  - `signal_decisions`
  - `telegram_messages` nếu có gửi
- `GET /api/v1/signals/{signal_id}` trả đúng schema đã công bố
- Config thresholds/cooldown thực sự đọc từ DB
- Có test tối thiểu cho các đường đi chính và regression từ findings QA

## Priority 0: Unblock App Startup Và Main Flow

### FIX-001: Thống nhất cách truy cập `settings`

Severity: `P0`

Vấn đề:
- `Settings` dùng field uppercase trong [app/core/config.py](/Users/minhhq/Documents/telegram-signal-bot/app/core/config.py:3)
- `app.main` và health controller lại gọi `settings.app_name`, `settings.app_version`, `settings.app_port`, `settings.app_env`

Việc cần làm:
- Chọn 1 style duy nhất:
  - Option A: đổi fields trong `Settings` sang lowercase theo convention docs
  - Option B: giữ uppercase và sửa mọi nơi gọi sang uppercase
- Ưu tiên Option A vì docs/convention đang nghiêng về lowercase-style access

Files:
- [app/core/config.py](/Users/minhhq/Documents/telegram-signal-bot/app/core/config.py:1)
- [app/main.py](/Users/minhhq/Documents/telegram-signal-bot/app/main.py:1)
- [app/api/health_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/health_controller.py:1)
- Các file khác đang đọc `settings.*`

QA verify:
- Import `app.main` không raise `AttributeError`
- `GET /api/v1/health` trả response hợp lệ

### FIX-002: Sửa controller gọi `SignalNormalizer` đúng signature

Severity: `P0`

Vấn đề:
- `SignalNormalizer.normalize(webhook_event_id, payload)`
- Controller đang gọi `SignalNormalizer.normalize(payload)`

Việc cần làm:
- Sửa call site để truyền đúng `webhook_event.id`
- Rà lại các hàm gọi khác nếu có

Files:
- [app/api/webhook_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/webhook_controller.py:66)
- [app/services/signal_normalizer.py](/Users/minhhq/Documents/telegram-signal-bot/app/services/signal_normalizer.py:8)

QA verify:
- Gửi payload hợp lệ không còn `TypeError`

### FIX-003: Sửa mismatch kiểu dữ liệu `FilterEngine` / controller / repo

Severity: `P0`

Vấn đề:
- `FilterEngine` đang trả `final_decision` và `route` dưới dạng string
- Controller lại dùng `.value`
- Controller truyền `channel_type` cho Telegram repo trong khi repo cần `route`
- Controller so sánh `status == "SENT"` nhưng `status` đang được dùng không nhất quán

Việc cần làm:
- Chốt 1 contract nhất quán:
  - hoặc `FilterEngine` trả enums thật
  - hoặc controller/repo dùng string nhất quán, không `.value`
- Đồng bộ payload key cho Telegram repo
- Đồng bộ kiểu trả về của notifier: string hay enum

Files:
- [app/services/filter_engine.py](/Users/minhhq/Documents/telegram-signal-bot/app/services/filter_engine.py:77)
- [app/api/webhook_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/webhook_controller.py:89)
- [app/repositories/telegram_repo.py](/Users/minhhq/Documents/telegram-signal-bot/app/repositories/telegram_repo.py:16)
- [app/services/telegram_notifier.py](/Users/minhhq/Documents/telegram-signal-bot/app/services/telegram_notifier.py:41)

QA verify:
- Happy path `PASS_MAIN` commit xong không crash
- `PASS_WARNING` path commit xong không crash

## Priority 1: Khôi phục Contract Payload Và Response

### FIX-004: Đưa request schema về đúng payload contract đã publish

Severity: `P0`

Vấn đề:
- Docs hiện tại dùng:
  - `metadata.entry`
  - `metadata.stop_loss`
  - `metadata.take_profit`
  - `timestamp` là ISO datetime
- Schema hiện tại lại dùng:
  - top-level `entry_price`
  - `tp`
  - `sl`
  - `timestamp: str | None`

Việc cần làm:
- Đồng bộ [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:43) với docs hiện tại
- Nếu team muốn đổi contract payload, phải cập nhật đồng bộ:
  - `docs/PAYLOAD_CONTRACT.md`
  - `docs/API_REFERENCE.md`
  - sample JSON
  - tests
- Theo QA, nên giữ docs contract hiện tại vì đó là contract đã công bố

Files:
- [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:1)
- [app/services/signal_normalizer.py](/Users/minhhq/Documents/telegram-signal-bot/app/services/signal_normalizer.py:17)
- [docs/PAYLOAD_CONTRACT.md](/Users/minhhq/Documents/telegram-signal-bot/docs/PAYLOAD_CONTRACT.md:1)
- [docs/API_REFERENCE.md](/Users/minhhq/Documents/telegram-signal-bot/docs/API_REFERENCE.md:1)
- [docs/examples/sample_long_5m.json](/Users/minhhq/Documents/telegram-signal-bot/docs/examples/sample_long_5m.json:1)
- [docs/examples/sample_short_squeeze_3m.json](/Users/minhhq/Documents/telegram-signal-bot/docs/examples/sample_short_squeeze_3m.json:1)

QA verify:
- Sample payload docs parse được qua Pydantic schema
- Normalizer map đúng fields sang DB model

### FIX-005: Sửa `SignalDetailResponse` cho khớp response thực tế của endpoint

Severity: `P1`

Vấn đề:
- Endpoint `/signals/{signal_id}` đang trả object nested
- `SignalDetailResponse` lại là object flat

Việc cần làm:
- Chọn 1 trong 2 hướng:
  - Option A: giữ nested response theo docs, sửa schema cho đúng
  - Option B: đổi endpoint trả flat response, nhưng phải sửa docs
- Theo docs hiện tại, nên chọn Option A

Files:
- [app/api/signal_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/signal_controller.py:11)
- [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:83)
- [docs/API_REFERENCE.md](/Users/minhhq/Documents/telegram-signal-bot/docs/API_REFERENCE.md:91)

QA verify:
- `GET /api/v1/signals/{signal_id}` pass response validation
- JSON shape khớp docs

### FIX-006: Chốt lại enum contract

Severity: `P1/P2`

Vấn đề:
- `DecisionType` chưa có `PENDING`
- `TelegramRoute.ADMIN` và DB schema/docs đã từng mismatch

Việc cần làm:
- Chốt final contract cho:
  - `DecisionType`
  - `TelegramRoute`
  - field nào được persist vào DB
- Đồng bộ code, migration, docs

Files:
- [app/core/enums.py](/Users/minhhq/Documents/telegram-signal-bot/app/core/enums.py:1)
- [app/domain/models.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/models.py:79)
- [migrations/001_init.sql](/Users/minhhq/Documents/telegram-signal-bot/migrations/001_init.sql:69)
- [docs/API_REFERENCE.md](/Users/minhhq/Documents/telegram-signal-bot/docs/API_REFERENCE.md:50)
- [docs/ARCHITECTURE.md](/Users/minhhq/Documents/telegram-signal-bot/docs/ARCHITECTURE.md:157)

QA verify:
- Enum set trong docs và code giống nhau
- Persist decision không vướng DB constraint

## Priority 2: Khôi phục Audit-First Và DB Config Contract

### FIX-007: Đồng bộ thiết kế `webhook_events` với audit-first contract

Severity: `P1`

Vấn đề:
- Controller ghi `source_ip`, `http_headers`, `raw_body`, `is_valid_json`
- Repo/model/migration lại dùng `ip_address`, `payload`, `auth_error`
- Thiếu khả năng lưu raw invalid JSON một cách faithful

Việc cần làm:
- Chốt schema `webhook_events` theo docs
- Đồng bộ controller, repository, ORM, migration
- Nếu muốn support invalid JSON đúng nghĩa:
  - thêm field raw text/body
  - phân biệt parsed JSON và raw body

Files:
- [app/api/webhook_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/webhook_controller.py:43)
- [app/repositories/webhook_event_repo.py](/Users/minhhq/Documents/telegram-signal-bot/app/repositories/webhook_event_repo.py:16)
- [app/domain/models.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/models.py:8)
- [migrations/001_init.sql](/Users/minhhq/Documents/telegram-signal-bot/migrations/001_init.sql:4)
- [docs/DATABASE_SCHEMA.md](/Users/minhhq/Documents/telegram-signal-bot/docs/DATABASE_SCHEMA.md:1)

QA verify:
- Invalid secret vẫn có webhook event row
- Invalid JSON vẫn có webhook event row
- Headers/source IP/raw body được lưu đúng như contract đã chốt

### FIX-008: Sửa config key mismatch để business config thực sự đọc từ DB

Severity: `P1`

Vấn đề:
- Repository query `"signal_bot_config"`
- Migration seed `"SIGNAL_BOT_CONFIG"`

Việc cần làm:
- Thống nhất config key exact-match trên toàn hệ thống
- Rà lại cả docs và test fixtures

Files:
- [app/repositories/config_repo.py](/Users/minhhq/Documents/telegram-signal-bot/app/repositories/config_repo.py:20)
- [migrations/001_init.sql](/Users/minhhq/Documents/telegram-signal-bot/migrations/001_init.sql:138)
- [docs/DATABASE_SCHEMA.md](/Users/minhhq/Documents/telegram-signal-bot/docs/DATABASE_SCHEMA.md:141)

QA verify:
- Đổi threshold trong DB có ảnh hưởng tới filter engine
- Không còn fallback silent về hardcoded defaults khi DB có config

### FIX-009: Rà lại timezone-aware persistence

Severity: `P1`

Vấn đề:
- Đây là finding cũ cần re-check sau khi code đã thay đổi
- Team đã chuyển nhiều cột sang `DateTime(timezone=True)`, nhưng cần verify toàn bộ model/migration/docs đã đồng bộ hết chưa

Việc cần làm:
- Soát hết timestamp fields trong ORM và migration
- Chốt tất cả timestamp lưu UTC-aware
- Kiểm tra parse timestamp từ payload trong normalizer

Files:
- [app/domain/models.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/models.py:1)
- [migrations/001_init.sql](/Users/minhhq/Documents/telegram-signal-bot/migrations/001_init.sql:1)
- [app/services/signal_normalizer.py](/Users/minhhq/Documents/telegram-signal-bot/app/services/signal_normalizer.py:37)

QA verify:
- Timestamp từ payload `...Z` persist và read back đúng UTC

## Priority 3: Close The Gaps In Behavior

### FIX-010: Chuẩn hóa `FilterEngine` types và naming

Severity: `P1`

Vấn đề:
- `FilterExecutionResult.final_decision` và `route` đang annotate là `str`
- Nhưng toàn flow business đang đối xử như enum
- `rule_group` đang dùng `Validation`/`Trading` khác style docs (`validation`/`trading`/`routing`)

Việc cần làm:
- Chuyển result model sang enums thật nếu team chọn typed flow
- Chuẩn hóa `rule_group` literals theo docs

Files:
- [app/services/filter_engine.py](/Users/minhhq/Documents/telegram-signal-bot/app/services/filter_engine.py:26)
- [docs/FILTER_RULES.md](/Users/minhhq/Documents/telegram-signal-bot/docs/FILTER_RULES.md:1)
- [docs/DATABASE_SCHEMA.md](/Users/minhhq/Documents/telegram-signal-bot/docs/DATABASE_SCHEMA.md:84)

QA verify:
- `signal_filter_results.rule_group` đúng taxonomy docs
- Không còn string/enum mismatch runtime

### FIX-011: Hoàn thiện logic controller cho HTTP errors đúng contract

Severity: `P1`

Vấn đề:
- Invalid secret hiện raise `HTTPException(..., detail="Invalid secret")`
- Nhưng docs yêu cầu error response có `status`, `error_code`, `message`

Việc cần làm:
- Trả đúng payload lỗi theo contract
- Xử lý rõ `INVALID_SCHEMA`, `UNSUPPORTED_TIMEFRAME`, `INVALID_SIGNAL_VALUES`, `INVALID_SECRET`

Files:
- [app/api/webhook_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/webhook_controller.py:52)
- [docs/API_REFERENCE.md](/Users/minhhq/Documents/telegram-signal-bot/docs/API_REFERENCE.md:72)

QA verify:
- 401/400 responses khớp contract docs từng case

### FIX-012: Hoàn thiện flow Telegram logging theo nguyên tắc persist-before-notify

Severity: `P1`

Vấn đề:
- Flow hiện tại đang notify trước commit cuối cùng
- Cần verify lại nguyên tắc `persist trước, notify sau`

Việc cần làm:
- Chốt transaction boundary:
  - commit webhook_event + signal + filter_results + decision trước
  - notify Telegram sau
  - telegram_messages commit riêng
- Xử lý `FAILED` log đúng khi Telegram timeout/error

Files:
- [app/api/webhook_controller.py](/Users/minhhq/Documents/telegram-signal-bot/app/api/webhook_controller.py:70)
- [docs/CONVENTIONS.md](/Users/minhhq/Documents/telegram-signal-bot/docs/CONVENTIONS.md:103)
- [AGENTS.md](/Users/minhhq/Documents/telegram-signal-bot/AGENTS.md:1)

QA verify:
- Telegram fail không rollback DB business records
- `telegram_messages` có `FAILED` khi send fail

## Priority 4: Test Coverage Tối Thiểu Để Khóa Regression

### FIX-013: Bổ sung unit tests cho regression blockers

Severity: `P0/P1`

Việc cần làm:
- Thêm test cho:
  - schema parse sample payload docs
  - normalizer signature + mapping
  - config key lookup
  - filter engine trả đúng type đã chốt

Files:
- `tests/unit/test_schemas.py`
- `tests/unit/test_signal_normalizer.py`
- `tests/unit/test_config_repo.py`
- [tests/unit/test_filter_engine.py](/Users/minhhq/Documents/telegram-signal-bot/tests/unit/test_filter_engine.py:1)

QA verify:
- Các blockers hiện tại có regression test riêng

### FIX-014: Bổ sung integration tests cho webhook

Severity: `P0/P1`

Việc cần làm:
- Thêm test cho:
  - valid payload -> `PASS_MAIN`
  - invalid secret -> 401 + audit row
  - duplicate -> 200 `DUPLICATE`
  - unsupported timeframe -> 400 + audit row
  - telegram fail -> business rows vẫn commit

Files:
- `tests/integration/test_webhook_endpoint.py`
- `tests/integration/test_audit_trail.py`
- `tests/integration/test_failure_handling.py`

QA verify:
- Có thể map trực tiếp với `docs/QA_STRATEGY.md` và `docs/TEST_CASES.md`

## Recommended Execution Order

1. `FIX-001`
2. `FIX-002`
3. `FIX-003`
4. `FIX-004`
5. `FIX-007`
6. `FIX-008`
7. `FIX-011`
8. `FIX-012`
9. `FIX-005`
10. `FIX-006`
11. `FIX-009`
12. `FIX-010`
13. `FIX-013`
14. `FIX-014`

## QA Exit Checklist

- App boot thành công với env hợp lệ
- Health endpoint pass
- Webhook valid payload pass không crash
- Webhook invalid secret trả đúng 401 contract
- Duplicate trả `200 DUPLICATE`
- DB config thực sự đọc từ `system_configs`
- Audit trail chứa đúng dữ liệu raw như contract đã chốt
- `/signals/{signal_id}` trả đúng shape docs
- Có regression tests cho toàn bộ P0 findings
