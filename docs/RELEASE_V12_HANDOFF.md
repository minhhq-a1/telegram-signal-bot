# Release 1.2 Handoff

## Branch

- Release branch: `release/1.2`
- Remote branch: `origin/release/1.2`
- Current head at handoff time: `c58194f`

---

## Scope delivered

### Phase A

- `A1` Verify/docs/build targets
- `A2` Correlation ID + pipeline summary log
- `A3` Health endpoints (`/health`, `/live`, `/ready`, `/deps`)
- `A4` Telegram notifier retry/client hardening

### Phase B

- `B1` Expanded `signal_outcomes` schema
- `B2` Outcome repository
- `B3` Outcome admin API
- `B4` Optional auto-create OPEN outcome for pass signals

### Phase C

- `C1` Outcome analytics endpoints
- `C2` Trading Ops Command Center dashboard
- `C3` Outcome CSV export

### Phase D

- `D1` Batch reverify endpoint
- `D2` Offline replay CLI
- `D3` Calibration report endpoint/service

### Phase E

- `E1` Config audit/versioning
- `E2` Config admin API
- `E3` Market context snapshot slice

---

## New migrations

- `006_v12_observability.sql`
- `007_v12_signal_outcomes.sql`
- `008_v12_config_audit.sql`
- `009_v12_market_context.sql`

---

## Important new endpoints

### Health / ops

- `GET /api/v1/health`
- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/health/deps`

### Outcomes

- `POST /api/v1/signals/{signal_id}/outcome/open`
- `PUT /api/v1/signals/{signal_id}/outcome`
- `GET /api/v1/signals/{signal_id}/outcome`
- `GET /api/v1/outcomes/recent`

### Analytics

- `GET /api/v1/analytics/outcomes/summary`
- `GET /api/v1/analytics/outcomes/by-bucket`
- `GET /api/v1/analytics/outcomes/rules`
- `GET /api/v1/analytics/ops-command-center`
- `GET /api/v1/analytics/export/outcomes.csv`
- `GET /api/v1/analytics/calibration/report`

### Reverify / replay

- `POST /api/v1/signals/reverify/batch`
- `GET /api/v1/signals/{signal_id}/reverify-results`
- CLI: `python3 scripts/replay_payloads.py --input <dir> --output <file>`

### Config admin

- `GET /api/v1/admin/config/signal-bot`
- `GET /api/v1/admin/config/audit-log`
- `PUT /api/v1/admin/config/signal-bot`

---

## Dashboard state

Dashboard đã được nâng lên hướng **Trading Ops Command Center** với:

- command header
- health pills
- ops snapshot cards
- signal radar
- risk & reliability alerts
- performance charts
- recent outcomes
- calibration placeholder section

Lưu ý:

- Dashboard hiện đã usable cho V1.2
- Vẫn nên có một vòng QA trực quan trên browser thật trước khi merge `release/1.2 -> main`

---

## Verification executed during implementation

Unit-level verification đã chạy nhiều lần xuyên suốt rollout, đặc biệt trên:

- `tests/unit/test_logging.py`
- `tests/unit/test_telegram_notifier.py`
- `tests/unit/test_replay_payloads.py`
- `tests/unit/test_calibration_report.py`
- `tests/unit/test_market_context_service.py`

Integration-scope commands cũng đã được chạy cho các slices liên quan, nhưng phần lớn đang `skip` khi thiếu biến môi trường `INTEGRATION_DATABASE_URL`.

### 2026-05-01 follow-up verification

Sau review release handoff, đã chạy lại verification trên PostgreSQL local từ `docker-compose.yml`:

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  rtk .venv/bin/python -m pytest tests/integration -q
```

Kết quả:

```text
114 passed in 78.83s (0:01:18)
```

Migration idempotency/status cũng đã chạy với DB local:

```bash
DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  rtk .venv/bin/python scripts/db/migrate.py apply
DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  rtk .venv/bin/python scripts/db/migrate.py status
```

Kết quả:

```text
skip all migrations (already applied)
ok migrations applied
applied 001 001_init.sql
applied 002 002_add_ops_migration_baseline.sql
applied 003 003_v11_upgrade.sql
applied 004 004_query_indexes.sql
applied 005 005_v11_config_idempotency_repair.sql
applied 006 006_v12_observability.sql
applied 007 007_v12_signal_outcomes.sql
applied 008 008_v12_config_audit.sql
applied 009 009_v12_market_context.sql
```

Unit/full local suite sau fixes:

```bash
rtk .venv/bin/python -m pytest -q
```

Kết quả trước khi bật integration env:

```text
141 passed, 114 skipped in 2.43s
```

Full suite với integration env bật sau follow-up fixes:

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  rtk .venv/bin/python -m pytest -q
```

Kết quả:

```text
255 passed in 85.38s (0:01:25)
```

Local smoke sau khi tạo `.env` local từ `.env.example` và reset migration metadata DB local:

```bash
rtk bash scripts/smoke_local.sh
```

Kết quả:

```text
valid: HTTP 200
duplicate: HTTP 200
invalid_json: HTTP 400
invalid_schema: HTTP 400
Smoke local completed successfully.
```

Lưu ý vận hành local: integration fixture có thể `drop_all()` app tables nhưng để lại `schema_migrations`; nếu dùng lại cùng database cho smoke sau integration, cần reset DB/migration metadata hoặc dùng DB riêng cho integration.

---

## Final verification still recommended

Trước khi merge `release/1.2 -> main`, nên chạy đầy đủ với PostgreSQL thật:

```bash
python3 -m pytest -q
python3 -m pytest tests/integration -q
bash scripts/smoke_local.sh
python3 scripts/db/migrate.py apply
python3 scripts/db/migrate.py status
```

Ghi chú: integration và migration replay đã pass trên PostgreSQL local ngày 2026-05-01; vẫn nên chạy lại trên staging/pre-prod trước merge chính thức.

Nếu có staging/pre-prod:

- verify dashboard `/dashboard`
- verify webhook happy path
- verify invalid JSON/schema/auth paths
- verify duplicate/idempotency path
- verify Telegram fail path
- verify outcome open/close flow
- verify calibration/export endpoints

---

## Known release caveats

- Integration suite đang phụ thuộc `INTEGRATION_DATABASE_URL`; nếu không set thì nhiều test bị skip.
- Một số feature V1.2 hiện đang ở mức functional-first, chưa phải polished/optimized tối đa.
- `MarketContextService` mới là slice nền tảng; chưa được cắm sâu vào filter routing production path.
- Command Center dashboard đã usable nhưng vẫn nên có một vòng visual QA thủ công.

---

## Suggested next action

1. Chạy full integration với DB thật
2. Chạy smoke + migration replay trên `release/1.2`
3. Review UI/UX dashboard trên browser thật
4. Mở PR: `release/1.2 -> main`
