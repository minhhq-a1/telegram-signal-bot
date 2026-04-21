# AGENTS.md — Signal Bot V1
# Shared rules: Antigravity + Claude.ai Projects
# Commit file này vào git

## Project

Telegram Signal Bot V1 — nhận webhook từ TradingView, lọc signal 2 lớp, gửi Telegram.
**Không auto-trade.**

## Tech Stack

- Python 3.12 + FastAPI 0.115
- SQLAlchemy 2.0 (style mới — dùng `select()`, không dùng `db.query()`)
- Pydantic v2
- PostgreSQL 16
- httpx (async)
- pytest

## Cấu trúc thư mục

```
app/api/          # FastAPI routers
app/core/         # config, enums, logging, database
app/domain/       # schemas.py (Pydantic) + models.py (ORM)
app/repositories/ # DB access layer
app/services/     # Business logic
migrations/       # Raw SQL — không dùng Alembic
docs/             # .md context files
```

## Nguyên tắc không được vi phạm

1. **Persist trước, notify sau** — không gửi Telegram trước `db.commit()`
2. **Idempotency** — `signal_id` đã tồn tại → return `200 DUPLICATE`, không insert lại
3. **Audit-first** — mọi webhook log vào `webhook_events`, kể cả invalid
4. **Config từ DB** — threshold/cooldown trong `system_configs`, không hardcode
5. **Không log secret** — `TRADINGVIEW_SHARED_SECRET` không được xuất hiện trong logs

## Filter Engine — Boolean Gate (không phải scoring)

Routing dựa trên FAIL/WARN, không dựa trên `server_score >= threshold`:

```
FAIL present          → REJECT   (NONE channel)
WARN MEDIUM+ present  → PASS_WARNING (WARN channel)
else                  → PASS_MAIN    (MAIN channel)
```

`server_score` vẫn tính và lưu DB để analytics — KHÔNG dùng để route.

## Coding Rules

- Type hints bắt buộc, dùng `str | None` (không dùng `Optional[str]`)
- `secrets.compare_digest()` cho mọi secret comparison
- `datetime.now(timezone.utc)` cho mọi timestamp
- UUID generate ở Python layer: `str(uuid.uuid4())`
- `filter_engine.run()` KHÔNG raise exception — luôn trả `FilterExecutionResult`
- Không hardcode threshold — đọc từ `system_configs` table

## Anti-patterns

```
❌ server_score >= threshold để route
❌ HTF_BIAS_CHECK dùng regime từ payload (circular dependency)
❌ db.query() — SQLAlchemy 1.x style
❌ Gửi Telegram trước db.commit()
❌ Log TRADINGVIEW_SHARED_SECRET
❌ Hardcode confidence threshold trong code
```

## Thứ tự implement

```
Phase 1: core/enums → core/config → core/database → domain/schemas → domain/models → migration
Phase 2: repositories (7 files) → services (5 files)
Phase 3: api controllers (3 files) → main.py → tests
```

## Docs reference

Chi tiết business logic nằm trong `docs/`:
- `FILTER_RULES.md` — rule engine + decision logic
- `PAYLOAD_CONTRACT.md` — payload fields + enums
- `DATABASE_SCHEMA.md` — DDL + indexes
- `TEST_CASES.md` — test cases với input/output
- `QA_STRATEGY.md` — acceptance criteria, missing TCs, pre-go-live checklist
