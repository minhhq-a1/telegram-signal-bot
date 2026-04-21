# Docs vs Implementation Gap List

Mục tiêu của file này là biến các mismatch giữa tài liệu và code hiện tại thành backlog thực dụng cho DEV.

Phạm vi review:
- `app/main.py`
- `app/core/enums.py`
- `app/domain/schemas.py`
- `app/domain/models.py`
- `migrations/001_init.sql`
- `README.md`
- `docs/API_REFERENCE.md`
- `docs/ARCHITECTURE.md`
- `docs/CONVENTIONS.md`
- `docs/PAYLOAD_CONTRACT.md`
- `docs/QA_STRATEGY.md`
- `docs/TASKS.md`

Quy ước severity:
- `P0`: blocker, không thể verify hoặc triển khai theo contract hiện tại
- `P1`: lệch contract nghiêm trọng, có nguy cơ làm sai hành vi hoặc sai audit trail
- `P2`: lệch vừa, dễ gây hiểu nhầm hoặc drift khi DEV tiếp tục build
- `P3`: cleanup/documentation alignment

## Backlog

| Gap ID | Severity | Area | Docs Source | Current Implementation | Required Change | Suggested Owner | QA Verification |
|---|---|---|---|---|---|---|---|
| GAP-001 | P0 | API | `README.md`, `docs/API_REFERENCE.md`, `docs/QA_STRATEGY.md` | [app/main.py](/Users/minhhq/Documents/telegram-signal-bot/app/main.py:1) chỉ có `GET /api/v1/health`; chưa có `POST /api/v1/webhooks/tradingview` và `GET /api/v1/signals/{signal_id}` | Tạo routers/controllers đúng contract và wire vào FastAPI app | Backend DEV | Smoke test được 3 endpoint; acceptance criteria không còn bị block bởi missing API |
| GAP-002 | P0 | Infrastructure | `README.md`, `docs/TASKS.md`, `docs/CONVENTIONS.md` | Chưa có `app/core/config.py`, `app/core/database.py`, `app/core/logging.py` | Implement settings, DB session dependency, structured logging như docs mô tả | Backend DEV | Import được settings, lấy được DB session, log không lộ secret |
| GAP-003 | P1 | Audit Trail | `AGENTS.md`, `docs/DATABASE_SCHEMA.md`, `docs/API_REFERENCE.md`, `docs/QA_STRATEGY.md` | `WebhookEvent.raw_body` ở [app/domain/models.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/models.py:17) là JSON object đã parse; không phù hợp để log malformed JSON | Đổi model/schema lưu raw request theo cách support invalid JSON thật sự, ví dụ thêm `raw_body_text` và giữ field parsed JSON riêng nếu cần | Backend DEV | Gửi body malformed vẫn insert được `webhook_events`; assert lưu được raw body và `INVALID_JSON` |
| GAP-004 | P1 | Timezone | `AGENTS.md`, `docs/PAYLOAD_CONTRACT.md`, `docs/CONVENTIONS.md` | Các cột thời gian trong [app/domain/models.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/models.py:14) dùng `DateTime` không timezone-aware | Chuẩn hóa ORM và migration theo UTC-aware timestamps | Backend DEV | Insert/read back timestamps vẫn giữ UTC semantics; test timezone round-trip pass |
| GAP-005 | P1 | Enums | `docs/API_REFERENCE.md`, `docs/PAYLOAD_CONTRACT.md` | [app/core/enums.py](/Users/minhhq/Documents/telegram-signal-bot/app/core/enums.py:8) thiếu `PENDING` trong `DecisionType` | Chốt contract: thêm `PENDING` vào enum hoặc sửa docs để bỏ `PENDING` nếu V1 không dùng async state | Backend DEV + Tech Lead | Response model và docs không còn mismatch; test schema serialize đúng enum set |
| GAP-006 | P1 | Routing | `docs/ARCHITECTURE.md`, `README.md`, `docs/DATABASE_SCHEMA.md` | [app/core/enums.py](/Users/minhhq/Documents/telegram-signal-bot/app/core/enums.py:14) có `TelegramRoute.ADMIN`, nhưng DB schema `signal_decisions.telegram_route` chỉ cho `MAIN`, `WARN`, `NONE` | Chốt rõ `ADMIN` là persisted decision route hay chỉ là notify side-channel; sửa enum hoặc schema/docs cho thống nhất | Backend DEV + Tech Lead | Persist decision không vi phạm DB constraint; test REJECT/admin path pass |
| GAP-007 | P1 | Docs Consistency | `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md` | `DecisionType` và `TelegramRoute` được mô tả khác nhau giữa 2 tài liệu | Chọn một source of truth, rồi đồng bộ toàn bộ docs liên quan | Tech Lead / Product Owner | Không còn enum list nào mâu thuẫn giữa docs |
| GAP-008 | P2 | Health API | `docs/API_REFERENCE.md` | Health response trong [app/main.py](/Users/minhhq/Documents/telegram-signal-bot/app/main.py:10) dùng `"Telegram Signal Bot"` thay vì `"telegram-signal-bot"` | Chuẩn hóa literal response hoặc sửa docs cho khớp | Backend DEV | Test exact health payload pass |
| GAP-009 | P2 | Error Contract | `docs/API_REFERENCE.md` | Chưa có schema riêng cho `404 SIGNAL_NOT_FOUND`; [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:55) chỉ có `ErrorResponse` dạng rejected chung | Thêm response model phù hợp cho not-found hoặc nới docs để dùng error model chung | Backend DEV | `GET /signals/{id}` not-found trả đúng payload đã chốt |
| GAP-010 | P2 | Schema Typing | `docs/CONVENTIONS.md`, `docs/ARCHITECTURE.md` | [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:60) dùng `str` cho `result`, `severity`, `telegram_route`, `delivery_status` thay vì enums | Dùng enums tương ứng trong response schemas để giảm drift | Backend DEV | MyPy/tests bắt được invalid enum value; OpenAPI hiển thị enum rõ ràng |
| GAP-011 | P2 | Base Metadata | `docs/TASKS.md`, `README.md` | `Base` đang nằm trong [app/domain/models.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/models.py:7), lệch với thiết kế `app/core/database.py` | Chuyển `Base` sang `app/core/database.py` và import lại từ models | Backend DEV | `Base.metadata.create_all(engine)` vẫn chạy; imports không circular |
| GAP-012 | P1 | ID Strategy | `AGENTS.md`, `docs/CONVENTIONS.md` | ORM và migration rely vào `gen_random_uuid()` DB-side; docs/rules yêu cầu generate UUID ở Python layer | Chọn một chiến lược duy nhất. Nếu theo project rule thì generate Python-side và bỏ phụ thuộc DB default | Backend DEV + Tech Lead | Tạo record mới không phụ thuộc DB default; tests có thể assert ID stable/predictable hơn |
| GAP-013 | P1 | Migration Robustness | `migrations/001_init.sql`, `docs/DATABASE_SCHEMA.md` | Migration dùng `gen_random_uuid()` nhưng không enable extension tương ứng | Thêm extension cần thiết hoặc bỏ DB-side UUID | Backend DEV | Migration chạy sạch trên database mới hoàn toàn |
| GAP-014 | P2 | Payload Normalization | `docs/PAYLOAD_CONTRACT.md`, `docs/ARCHITECTURE.md` | `metadata.squeeze_on` và `squeeze_fired` là `int` ở request schema nhưng là `bool` ở ORM model | Document và implement rõ normalize `0/1` -> `bool` ở service layer | Backend DEV | Parse sample payload và persist đúng kiểu; tests khẳng định normalization |
| GAP-015 | P2 | Validation | `docs/CONVENTIONS.md`, `docs/TASKS.md` | [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:33) chưa có validators strip/normalize cho `symbol`, `timeframe`, `source` | Thêm validators theo convention | Backend DEV | Input có space/lowercase được normalize hoặc reject đúng như đã chốt |
| GAP-016 | P3 | Code Hygiene | `docs/CONVENTIONS.md` | [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:4) import `field_validator` và `AuthStatus` nhưng chưa dùng | Dùng thật hoặc bỏ import thừa | Backend DEV | Lint/ruff sạch hơn; không còn dead imports |
| GAP-017 | P2 | Schema Defaults | `docs/CONVENTIONS.md` | [app/domain/schemas.py](/Users/minhhq/Documents/telegram-signal-bot/app/domain/schemas.py:109) dùng mutable list default trực tiếp | Chuyển sang `Field(default_factory=list)` | Backend DEV | Schema behavior ổn định; không có mutable-default warning |
| GAP-018 | P1 | Auth Design Docs | `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md` | API docs ghi secret nằm trong body; architecture docs lại ghi “secret header check” | Sửa docs kiến trúc để thống nhất auth bằng request body như payload contract | Tech Lead / Product Owner | Tài liệu không còn hướng DEV implement sai auth source |
| GAP-019 | P1 | Invalid Schema Semantics | `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md`, `docs/QA_STRATEGY.md` | Architecture docs đang gắn invalid schema với `is_valid_json=false`, trong khi invalid schema vẫn có thể là JSON hợp lệ | Sửa docs để phân biệt `INVALID_JSON` và `INVALID_SCHEMA` đúng semantics | Tech Lead / QA | Test case cho invalid JSON và invalid schema assert khác nhau, rõ ràng |
| GAP-020 | P2 | README Accuracy | `README.md` | README liệt kê nhiều file/service/repository chưa tồn tại như thể đã implement | Đánh dấu rõ đây là target structure hoặc cập nhật README theo trạng thái scaffold hiện tại | Tech Lead / Product Owner | Onboarding dev mới không bị kỳ vọng sai về mức độ hoàn thiện của repo |
| GAP-021 | P1 | Quick Start | `README.md` | README hướng dẫn `curl` webhook ngay, nhưng app chưa có webhook endpoint | Tạm chỉnh README hoặc ưu tiên implement endpoint trước | Backend DEV + Tech Lead | Quick start chạy theo README không bị fail ở bước webhook |
| GAP-022 | P2 | Timeframe Messaging | `README.md`, `docs/PAYLOAD_CONTRACT.md`, `docs/FILTER_RULES.md` | README nói indicator hỗ trợ nhiều TF; dễ bị hiểu là bot hỗ trợ luôn toàn bộ TF đó | Chỉnh wording để tách biệt capability của indicator và whitelist server V1 | Product Owner | Không còn hiểu lầm “indicator support = backend support” |
| GAP-023 | P2 | Score Messaging | `docs/FILTER_RULES.md`, `docs/API_REFERENCE.md` | FILTER_RULES nói score không được route, nhưng message/API examples vẫn nhấn mạnh score khá mạnh | Chèn note rõ `server_score` chỉ để analytics/debug, không tham gia routing | Tech Lead / Product Owner | DEV mới đọc docs không vô tình implement route theo score |
| GAP-024 | P0 | Test Readiness | `docs/QA_STRATEGY.md`, `docs/TEST_CASES.md` | Repo chưa có thư mục `tests/` dù test plan đã được viết khá chi tiết | Dựng test skeleton tối thiểu cho webhook, duplicate, audit trail, Telegram fail | QA + Backend DEV | Có thể chạy pytest với ít nhất smoke + 2-3 integration cases đầu tiên |
| GAP-025 | P2 | Task Tracking | `docs/TASKS.md` | Task docs mô tả tiến độ phase xa hơn trạng thái repo hiện tại | Cập nhật task status hoặc gắn checkbox/trạng thái thực tế | Tech Lead | Backlog phản ánh đúng trạng thái thực tế để tránh lệch kỳ vọng |
| GAP-026 | P3 | Dependency Docs | `docs/TASKS.md`, `requirements.txt` | `requirements.txt` có `respx`, nhưng TASK-001 sample requirements chưa phản ánh | Đồng bộ docs requirements với file thực tế | Backend DEV | DEV setup môi trường chỉ theo docs vẫn đủ dependency |

## Suggested Execution Order

1. `GAP-001`, `GAP-002`, `GAP-024`
2. `GAP-003`, `GAP-004`, `GAP-012`, `GAP-013`
3. `GAP-005`, `GAP-006`, `GAP-007`, `GAP-018`, `GAP-019`
4. `GAP-009`, `GAP-010`, `GAP-014`, `GAP-015`, `GAP-017`
5. `GAP-008`, `GAP-020`, `GAP-021`, `GAP-022`, `GAP-023`, `GAP-025`, `GAP-026`

## Notes For DEV

- Trước khi code tiếp phần service/controller, nên chốt trước contract cho:
  - `DecisionType`
  - `TelegramRoute`
  - chiến lược UUID
  - semantics của `INVALID_JSON` vs `INVALID_SCHEMA`
- Nếu chưa chốt các điểm này, rất dễ phải sửa lại test, migration, và response model cùng lúc.
- Priority kỹ thuật cao nhất theo QA là:
  - audit-first thực sự hoạt động với invalid JSON
  - timezone UTC không bị mất khi persist/read
  - webhook endpoint và DB wiring phải tồn tại để bắt đầu integration testing

## Notes For QA

- Không nên viết full integration suite trước khi `GAP-001`, `GAP-002`, `GAP-003`, `GAP-004` được xử lý.
- Sau khi DEV fix nhóm gap đầu tiên, ưu tiên verify lại:
  - invalid secret vẫn tạo `webhook_events`
  - invalid JSON vẫn có audit row
  - duplicate `signal_id` trả `200 DUPLICATE`
  - Telegram failure không rollback signal + filter + decision
