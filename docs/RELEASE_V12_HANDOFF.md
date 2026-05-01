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

