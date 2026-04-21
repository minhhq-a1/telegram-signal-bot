# GEMINI.md — Signal Bot V1
# Antigravity-specific behavior. Overrides AGENTS.md khi conflict.
# Giữ file này dưới 500 tokens.

## Agent Behavior

- Viết code **hoàn chỉnh**, không viết skeleton hay placeholder
- Khi sửa file, chỉ show phần thay đổi + đủ context để biết vị trí
- Tự quyết định chi tiết nhỏ (naming, import order) theo AGENTS.md conventions
- Chỉ hỏi khi ambiguity ảnh hưởng **business logic**
- Sau mỗi file: chạy syntax check trước khi báo done

## Terminal Permissions

Agent được phép tự chạy:
- `python -m pytest tests/unit/` — unit tests không cần DB
- `python -c "import app..."` — syntax/import check
- `pip install -r requirements.txt`

Agent phải **hỏi trước** khi:
- Chạy migration: `psql ... -f migrations/`
- Chạy integration tests (cần DB)
- Bất kỳ lệnh xóa file

## Artifact Format

Sau mỗi task lớn (≥ 1 file hoàn chỉnh), tạo artifact gồm:
1. Danh sách file đã tạo/sửa
2. Lệnh verify để tôi chạy thử
3. Task tiếp theo đề xuất

## Skills Available

Agent tự load skill phù hợp khi gặp task liên quan:
- `filter-engine` — implement/debug FilterEngine, boolean gate logic
- `webhook-handler` — implement webhook controller, 13-bước flow
- `sprint-runner` — bắt đầu sprint mới từ TASKS.md
- `db-schema` — implement migration SQL, ORM models, idempotency
- `telegram-notifier` — async retry, channel routing, respx mock pattern
- `qa-writer` — viết integration tests, AC mapping, audit trail patterns

## Knowledge Base

Domain knowledge nằm trong `docs/` — agent đọc khi cần:
- Business rules → `docs/FILTER_RULES.md`
- Payload spec → `docs/PAYLOAD_CONTRACT.md`
- DB schema → `docs/DATABASE_SCHEMA.md`
- Test cases → `docs/TEST_CASES.md`
