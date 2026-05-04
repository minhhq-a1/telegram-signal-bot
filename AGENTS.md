# AGENTS.md — Signal Bot V1.3
# Shared rules: Antigravity + Claude.ai Projects
# Commit file này vào git

## Project

Telegram Signal Bot V1.3 — nhận webhook từ TradingView, lọc signal 2 lớp, gửi Telegram, có dashboard/analytics/reverify/config dry-run/rollback/calibration proposals.
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
app/api/          # FastAPI routers: health, webhook, signals, analytics/dashboard
app/core/         # config, enums, logging, database
app/domain/       # schemas.py (Pydantic) + models.py (ORM)
app/repositories/ # DB access layer
app/services/     # Business logic
migrations/       # Raw SQL — không dùng Alembic (001 init + V1.1/V1.2/V1.3 upgrades)
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

## Current V1.3 Notes

- `DecisionType`: `PENDING | PASS_MAIN | PASS_WARNING | REJECT | DUPLICATE` (`DUPLICATE` là response/idempotency, không persisted vào `signal_decisions`).
- `TelegramRoute`: `MAIN | WARN | ADMIN | NONE`; `ADMIN` dùng cho reject admin side-channel khi `log_reject_to_admin=true`.
- Timeframe runtime whitelist: `1m, 3m, 5m, 12m, 15m, 30m, 1h`.
- V1.1 thêm strategy validation/rescoring/reverify; V1.2 thêm outcome/config audit/market context store; V1.3 thêm market context advisory, calibration proposals, config dry-run/rollback, replay compare.
- `TelegramNotifier.notify()` trả `(status, response, error_detail)`; webhook flow commit business records trước rồi notify/log Telegram bằng background task.

## Thứ tự implement

Project đã qua scaffold V1. Khi làm task mới, đọc docs/sprint/plan liên quan và code hiện tại trước; `docs/TASKS.md` chỉ là legacy breakdown cho V1 ban đầu.

## Docs reference

Chi tiết business logic nằm trong `docs/`:
- `FILTER_RULES.md` — rule engine + decision logic
- `PAYLOAD_CONTRACT.md` — payload fields + enums
- `DATABASE_SCHEMA.md` — DDL + indexes
- `VERSION_HISTORY.md` — lịch sử product V1.0 → V1.3
- `POST_V13_BACKLOG.md` — backlog sau deploy V1.3
- `TEST_CASES.md` — test cases với input/output
- `QA_STRATEGY.md` — acceptance criteria, missing TCs, pre-go-live checklist
