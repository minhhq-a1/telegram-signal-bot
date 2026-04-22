# Architecture Remediation Plan — Signal Bot V1

## Mục tiêu

Tài liệu này chuyển các findings từ review kiến trúc thành kế hoạch sửa cụ thể,
ưu tiên theo mức độ rủi ro production.

Nguyên tắc giữ nguyên:
- Persist trước, notify sau
- Idempotency trả `200 DUPLICATE`, không để leak `500`
- Audit-first cho mọi webhook
- Config runtime đọc từ `system_configs`
- Không log secret

---

## Priority 0 — Must Fix Trước Production

### P0.1 Atomic idempotency ở DB boundary

**Vấn đề hiện tại**
- Luồng hiện tại check `find_by_signal_id()` rồi mới insert.
- Hai request cùng lúc có thể cùng vượt qua bước check và một request fail vì unique constraint.

**Thiết kế mục tiêu**
- `signals.signal_id` unique constraint là source of truth cuối cùng.
- Application phải graceful-handle duplicate tại thời điểm insert.
- Kết quả mong muốn:
  - request A: xử lý bình thường
  - request B: trả `200 DUPLICATE`
  - không request nào rơi `500` chỉ vì duplicate race

**Files dự kiến sửa**
- `app/api/webhook_controller.py`
- `app/repositories/signal_repo.py`
- có thể thêm helper transaction trong `app/core/database.py`
- tests:
  - `tests/integration/test_webhook_endpoint.py`
  - `tests/integration/test_api_regressions.py`

**Implementation outline**
1. Giữ pre-check `find_by_signal_id()` như fast-path tùy chọn, nhưng không coi là đủ.
2. Bọc `signal_repo.create()` bằng handling cho `sqlalchemy.exc.IntegrityError`.
3. Khi gặp duplicate unique `signal_id`:
   - rollback về transaction state an toàn
   - không insert filter_results / decision / telegram log
   - trả `WebhookAcceptedResponse(decision=DUPLICATE)`
4. Nếu cần, dùng nested transaction hoặc savepoint để không làm mất `webhook_event` đã audit trước đó.

**Acceptance criteria**
- Hai request đồng thời cùng `signal_id` không tạo ra `500`
- DB chỉ có 1 row trong `signals`
- Không có orphan `signal_filter_results`, `signal_decisions`, `telegram_messages`

**Suggested tests**
- concurrent insert cùng `signal_id`
- duplicate race sau khi audit row đã được tạo

---

### P0.2 Chuẩn hóa contract của `signal_id`

**Vấn đề hiện tại**
- Nếu payload không có `signal_id`, controller tự ghép `symbol-timeframe-signal-price`.
- Fingerprint này quá yếu và có thể nuốt mất signal hợp lệ khác bar.

**Thiết kế mục tiêu**
- Ưu tiên mạnh nhất: bắt buộc TradingView luôn gửi `signal_id`.
- Nếu business bắt buộc hỗ trợ fallback:
  - fingerprint phải bao gồm ngữ cảnh bar và trade geometry
  - ví dụ: `symbol`, `timeframe`, `signal`, `bar_time|timestamp`, `entry`, `stop_loss`, `take_profit`

**Files dự kiến sửa**
- `app/domain/schemas.py`
- `app/api/webhook_controller.py`
- `docs/PAYLOAD_CONTRACT.md`
- `docs/API_REFERENCE.md`
- tests:
  - `tests/integration/test_webhook_endpoint.py`
  - `tests/unit/test_signal_normalizer.py`

**Recommended decision**
- Với production safety, nên nâng `signal_id` thành required field trong payload contract.

**Acceptance criteria**
- Không còn fallback yếu dựa trên `price` đơn lẻ
- Payload contract và implementation thống nhất
- Test phân biệt được 2 signal khác bar nhưng cùng price

---

### P0.3 Thống nhất config runtime contract

**Vấn đề hiện tại**
- `Settings` có `enable_news_block`
- `system_configs.signal_bot_config` không seed key này
- `FilterEngine` lại lookup `ENABLE_NEWS_BLOCK`
- Result: khó biết nguồn truth thật sự là gì

**Thiết kế mục tiêu**
- Filter runtime config có một contract duy nhất trong DB JSON:
  - dùng snake_case
  - ví dụ `enable_news_block`
- Env chỉ giữ config hạ tầng hoặc bootstrap, không override rule logic âm thầm.

**Files dự kiến sửa**
- `app/services/filter_engine.py`
- `app/repositories/config_repo.py`
- `app/core/config.py`
- `migrations/001_init.sql`
- docs:
  - `docs/DATABASE_SCHEMA.md`
  - `docs/FILTER_RULES.md`
- tests:
  - `tests/unit/test_filter_engine.py`
  - `tests/integration/test_api_regressions.py`

**Implementation outline**
1. Đổi mọi key filter config về snake_case.
2. Seed thêm `enable_news_block` trong migration/config docs.
3. `FilterEngine` chỉ đọc `enable_news_block`.
4. Quyết định rõ fallback khi DB thiếu key:
   - khuyến nghị: fallback theo documented default rồi log warning.

**Acceptance criteria**
- Tắt `enable_news_block` trong DB có hiệu lực thật
- Không còn lookup key kiểu uppercase không documented
- Docs, migration, code cùng một schema config

---

### P0.4 Tách orchestration flow khỏi controller

**Vấn đề hiện tại**
- `webhook_controller` đang chứa toàn bộ use case nghiệp vụ.
- Điều này làm transaction boundary, reuse, replay và test flow khó hơn.

**Thiết kế mục tiêu**
- Controller chỉ làm HTTP boundary:
  - đọc request
  - map response/status code
  - gọi application service
- Một service điều phối chịu trách nhiệm:
  - audit webhook
  - auth
  - idempotency
  - normalize
  - filter
  - persist decision
  - notify + log delivery

**Files dự kiến sửa**
- thêm mới:
  - `app/services/webhook_ingestion_service.py` hoặc `app/services/signal_processing_service.py`
- chỉnh:
  - `app/api/webhook_controller.py`
  - có thể `app/services/message_renderer.py`, `app/services/telegram_notifier.py`
- tests:
  - integration hiện có
  - unit mới cho orchestration service

**Suggested service responsibilities**
- `WebhookIngestionService.handle_raw_request(...)`
- `SignalProcessingService.process_valid_payload(...)`

**Acceptance criteria**
- Controller còn mỏng, dễ đọc
- Business flow có thể được test không cần gọi HTTP layer
- Chuẩn bị sẵn cho background queue hoặc replay job trong tương lai

---

## Priority 1 — Nên Refactor Ngay Sau P0

### P1.1 Tách transaction thành 2 phase rõ ràng

**Phase A**
- `webhook_events`
- `signals`
- `signal_filter_results`
- `signal_decisions`
- `commit`

**Phase B**
- Telegram send
- `telegram_messages`
- `commit`

**Mục tiêu**
- Làm rõ boundary thay vì để logic dàn phẳng trong endpoint/service.

---

### P1.2 Làm rõ interfaces mà `FilterEngine` phụ thuộc

**Vấn đề**
- Engine đang phụ thuộc trực tiếp vào repository concrete.

**Mục tiêu**
- Giảm coupling persistence:
  - `DuplicateSignalGateway`
  - `CooldownGateway`
  - `MarketEventGateway`

**Lợi ích**
- test engine gọn hơn
- dễ thay backend query hoặc caching strategy

---

### P1.3 Nâng chất lượng audit cho `decision_reason`

**Vấn đề**
- `decision_reason` hiện còn khá generic.

**Mục tiêu**
- Lưu được rule chính gây reject/warn.
- Ví dụ:
  - `primary_rule_code`
  - `warning_rule_codes`
  - hoặc chi tiết hơn trong `decision_reason`

**Lợi ích**
- analytics rõ hơn
- QA trace nhanh hơn
- dashboard giải thích được tại sao signal bị downgrade/reject

---

### P1.4 Tăng bảo vệ logging khỏi secret leakage

**Vấn đề**
- Hiện tại chưa thấy log secret trực tiếp, nhưng chưa có cơ chế sanitize tập trung.

**Mục tiêu**
- `logging` formatter hoặc helper strip các key nhạy cảm:
  - `secret`
  - `token`
  - `authorization`
  - `password`

**Files dự kiến sửa**
- `app/core/logging.py`
- các chỗ log payload nếu có

---

## Priority 2 — Có Thể Đẩy Sang V1.1

### P2.1 Telegram delivery qua outbox/background worker

**Khi nào cần**
- webhook volume tăng
- muốn giảm latency response
- cần retry độc lập với request lifecycle

**Lưu ý**
- Vẫn phải giữ nguyên nguyên tắc `persist trước, notify sau`

---

### P2.2 Tách analytics read model

**Vấn đề hiện tại**
- `analytics_controller` query trực tiếp transactional tables.

**Chấp nhận cho V1**
- hoàn toàn ổn khi volume thấp

**V1.1**
- materialized view
- summary table
- async aggregation job

---

### P2.3 Thay payload-derived regime/news bằng independent data

**Mục tiêu**
- giảm circular dependency trong filter quality
- tăng độ tin cậy của hard blocks/warnings

---

## Thứ Tự Thực Thi Khuyến Nghị

1. Atomic idempotency
2. Chuẩn hóa `signal_id`
3. Thống nhất config runtime contract
4. Extract orchestration service
5. Tách transaction phases rõ ràng
6. Tăng observability cho decision/audit
7. Logging sanitizer

---

## Checklist Verify Sau Mỗi Bước

### Sau P0.1
- `pytest` pass
- test concurrent duplicate pass
- không còn `500` do race idempotency

### Sau P0.2
- docs payload cập nhật
- contract test pass
- không còn fallback yếu dựa trên `price`

### Sau P0.3
- sửa config trong DB có hiệu lực đúng
- unit test cho `enable_news_block` pass
- docs config và migration khớp code

### Sau P0.4
- controller giảm đáng kể số dòng orchestration
- integration test không đổi hành vi API contract
- service unit tests cover happy path, invalid secret, duplicate, telegram fail

---

## Definition of Done

Một remediation item được coi là hoàn thành khi:
- code đã sửa
- test mới đã thêm cho bug/risk tương ứng
- docs liên quan đã cập nhật
- không vi phạm các nguyên tắc trong `AGENTS.md`
- không làm thay đổi contract bên ngoài nếu chưa có chủ đích rõ ràng
