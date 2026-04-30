# ROADMAP V1.2 — Paper Trading Intelligence & Production Hardening
<!--
  Roadmap executable cho Telegram Signal Bot sau V1.1.
  Mục tiêu: chạy paper trading an toàn, thu outcome data, hiệu chỉnh filter bằng dữ liệu thật.
  Không auto-trade trong V1.2.
-->

## 0. Executive Summary

V1.1 đã có nền tảng tốt: TradingView webhook, audit trail, idempotency, boolean filter gate, Telegram routing, dashboard, analytics, reverify, reject analytics và rate limiting.

V1.2 không nên thêm auto-trade. V1.2 tập trung vào 4 mục tiêu:

1. **Production hardening** — chạy ổn định 24/7, dễ debug, không mất audit.
2. **Paper trading outcome loop** — lưu kết quả TP/SL/MFE/MAE để đo chất lượng signal.
3. **Data-driven calibration** — đề xuất chỉnh threshold/rule dựa trên outcome thật, tránh overfit.
4. **Operational dashboard** — dashboard phục vụ quyết định vận hành, không chỉ xem signal list.

North Star Metric cho V1.2:

```text
Mỗi signal có thể trace đầy đủ:
webhook_event -> signal -> filter_results -> decision -> telegram_message -> outcome -> analytics report
```

---

## 1. Non-Negotiable Invariants

Mọi task V1.2 phải giữ nguyên các rule sau:

1. **Persist before notify** — không gửi Telegram trước khi commit business records.
2. **Idempotency** — `signal_id` đã tồn tại trả `200 DUPLICATE`, không insert signal/filter/decision lần hai.
3. **Audit-first** — mọi webhook phải log vào `webhook_events`, kể cả invalid JSON/schema/auth.
4. **DB config first** — threshold/cooldown/operational config đọc từ `system_configs`, không hardcode logic vận hành mới trong code.
5. **No secret logging** — không log TradingView secret, Telegram token, dashboard token, auth headers nhạy cảm.
6. **Boolean gate routing** — routing dựa trên FAIL/WARN, không dựa trên `server_score >= threshold`.
7. **SQLAlchemy 2.0 style** — dùng `select()`, không dùng `db.query()` trong `app/`.
8. **Python 3.12 typing** — dùng `str | None`, không dùng `Optional[str]`.
9. **UTC timestamps** — dùng `datetime.now(timezone.utc)`.
10. **Python UUID generation** — dùng `str(uuid.uuid4())` ở Python layer.
11. **No auto-trade** — V1.2 chỉ paper trading, analytics, admin tooling.

---

## 2. Current State Snapshot

### Đã có

- `POST /api/v1/webhooks/tradingview` nhận payload TradingView.
- `WebhookIngestionService` xử lý parse/validate/auth/idempotency/filter/persist/notify.
- `FilterEngine` chạy boolean gate với `FilterExecutionResult`.
- `StrategyValidator` và `RescoringEngine` cho V1.1 pilot rules.
- Telegram route: `MAIN`, `WARN`, `ADMIN`, `NONE`.
- Dashboard static HTML tại `/dashboard` có token auth.
- Analytics endpoints: summary, timeline, filter stats, daily, reject stats.
- Reverify endpoint và reverify history endpoint.
- Rate limit webhook bằng `slowapi`.
- Test suite unit + integration hiện có.

### Khoảng trống chính

- `SignalOutcome` mới là stub, chưa có endpoint/repository đầy đủ để ghi outcome paper trading.
- Chưa có report win rate/expectancy/R-multiple theo strategy/timeframe/rule.
- Chưa có config versioning/audit cho thay đổi rule.
- Chưa có batch replay/calibration framework.
- Market regime/vol regime vẫn phụ thuộc payload indicator, còn circular dependency.
- Observability còn thiếu correlation ID, pipeline summary log, dependency health.
- Telegram delivery chưa tối ưu connection reuse/retry policy production-grade.

---

## 3. V1.2 Scope

### In scope

- Production readiness hardening.
- Better health checks and observability.
- Outcome tracking for paper trading.
- Outcome analytics and dashboard upgrades.
- Batch reverify/replay foundation.
- Config audit/versioning foundation.
- Optional independent market context design + first implementation slice.

### Out of scope

- Auto-trading or broker execution.
- ML model training for live routing.
- Paid market data dependency as mandatory requirement.
- Multi-tenant/user account system.
- Major frontend framework rewrite.

---

## 4. Release Plan

```text
V1.2.0  Production hardening + observability
V1.2.1  Paper outcome tracking APIs + tests
V1.2.2  Outcome analytics + dashboard report
V1.2.3  Batch replay/reverify + calibration report
V1.2.4  Config audit/versioning + optional market context slice
```

Recommended execution order:

1. Phase A — Safety and operability.
2. Phase B — Outcome data model and API.
3. Phase C — Analytics/dashboard based on outcome.
4. Phase D — Replay/calibration tooling.
5. Phase E — Config audit and independent market context.

---

# Phase A — Production Hardening

## A1. Repository Hygiene and Verify Targets

### Goal

Chuẩn hóa lệnh verify để mọi PR V1.2 có cùng definition of done.

### Scope

Files:

- `Makefile`
- `README.md`
- `docs/LOCAL_SMOKE_CHECKLIST.md`
- `docs/QA_STRATEGY.md`

### Spec

Add/verify Make targets:

```makefile
test-unit:
	python -m pytest tests/unit -q

test-integration:
	python -m pytest tests/integration -q

test:
	python -m pytest -q

smoke-local:
	bash scripts/smoke_local.sh

migrate:
	python scripts/db/migrate.py
```

Update docs with standard commands:

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest -q
bash scripts/smoke_local.sh
```

### Acceptance Criteria

- `make test-unit` passes.
- `make test` passes when DB/test env is available.
- Docs mention one canonical verify flow.

---

## A2. Correlation ID and Pipeline Summary Log

### Goal

Mỗi webhook có một correlation ID để trace qua logs và DB artifacts.

### Scope

Files:

- `app/services/webhook_ingestion_service.py`
- `app/core/logging.py`
- `app/repositories/webhook_event_repo.py`
- `app/domain/models.py`
- `migrations/006_v12_observability.sql`
- `tests/integration/test_webhook_endpoint.py`
- `tests/unit/test_logging.py`

### Schema

Add nullable columns:

```sql
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(64);
ALTER TABLE signals ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_webhook_events_correlation_id ON webhook_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_signals_correlation_id ON signals(correlation_id);
```

### Behavior

- Generate `correlation_id = str(uuid.uuid4())` at start of `WebhookIngestionService.ingest()`.
- If request header `X-Correlation-ID` exists and is safe length (`<=64`), use it; otherwise generate.
- Store correlation ID in `webhook_events` and `signals`.
- Include correlation ID in structured logs.
- Add one pipeline summary log after business commit:

```json
{
  "event": "webhook_pipeline_completed",
  "correlation_id": "6f8f4f28-9d68-4d1e-9c12-3d2a1b0f7c44",
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "decision": "PASS_MAIN",
  "route": "MAIN",
  "failed_rules": [],
  "warn_rules": ["LOW_VOLUME_WARNING"],
  "duration_ms": 42,
  "notification_enqueued": true
}
```

### Security

- Do not log payload secret.
- Do not log raw headers except redacted fields.

### Acceptance Criteria

- Valid webhook stores same `correlation_id` on `webhook_events` and `signals`.
- Invalid JSON still logs `correlation_id` on `webhook_events`.
- Logs contain `webhook_pipeline_completed` for non-error processed signals.
- Tests verify no secret appears in logs.

---

## A3. Health Readiness Endpoints

### Goal

Tách liveness/readiness/dependency checks để deploy dễ hơn.

### Scope

Files:

- `app/api/health_controller.py`
- `tests/integration/test_api_regressions.py`

### Endpoints

```http
GET /api/v1/health/live
GET /api/v1/health/ready
GET /api/v1/health/deps
```

### Contract

`/live`:

```json
{"status":"ok","service":"telegram-signal-bot","version":"1.2.x"}
```

`/ready` checks:

- DB connection works with `SELECT 1`.
- `ConfigRepository.get_signal_bot_config()` returns required keys:
  - `allowed_symbols`
  - `allowed_timeframes`
  - `confidence_thresholds`
  - `cooldown_minutes`
  - `rr_min_base`
  - `rr_min_squeeze`

Response:

```json
{
  "status": "ok",
  "checks": {"database": "ok", "config": "ok"}
}
```

`/deps` checks:

- DB ok.
- Telegram config present.
- Do not send Telegram message.

If dependency fails, return `503` with details.

### Acceptance Criteria

- `/live` does not require DB.
- `/ready` returns `503` if DB query fails.
- `/deps` never sends a Telegram message.

---

## A4. Telegram Notifier Connection Reuse and Retry

### Goal

Giảm overhead và tăng độ bền khi Telegram 429/5xx/network lỗi.

### Scope

Files:

- `app/services/telegram_notifier.py`
- `app/services/webhook_ingestion_service.py`
- `tests/unit/test_telegram_notifier.py`
- `tests/integration/test_webhook_endpoint.py`

### Spec

- Use one reusable `httpx.AsyncClient` per notifier instance or app lifespan.
- Retry only for:
  - network timeout/connect errors
  - HTTP `429`
  - HTTP `500-599`
- Do not retry for:
  - `400`
  - `401`
  - invalid route/chat id
- Retry policy:

```text
attempts: 3
backoff: 0.5s, 1s, 2s
jitter: optional small random 0-100ms
```

- `TelegramNotifier.notify()` keeps contract:

```python
async def notify(route: str, message_text: str) -> tuple[str, dict | None, str | None]
```

- Delivery log still happens in background task after business commit.

### Acceptance Criteria

- 429 then success results in `SENT`.
- 401 results in `FAILED` without retry.
- Network exception after all attempts returns `FAILED` with error detail.
- Webhook response remains 200 if Telegram fails.

---

# Phase B — Paper Trading Outcome Tracking

## B1. Outcome Schema Upgrade

### Goal

Mở rộng `signal_outcomes` để lưu kết quả paper trading đủ phân tích.

### Scope

Files:

- `app/domain/models.py`
- `migrations/007_v12_signal_outcomes.sql`
- `docs/DATABASE_SCHEMA.md`

### Schema

Current table has basic fields. Extend with:

```sql
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS outcome_status VARCHAR(32);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS close_reason VARCHAR(32);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS entry_price NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS stop_loss NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS take_profit NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS max_favorable_price NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS max_adverse_price NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(10,4);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(10,4);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(10,4);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS opened_at TIMESTAMP;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_status ON signal_outcomes(outcome_status);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_closed_at ON signal_outcomes(closed_at);
```

Enums by convention:

```text
outcome_status: OPEN | CLOSED | CANCELED | INVALIDATED
close_reason: TP_HIT | SL_HIT | MANUAL_CLOSE | EXPIRED | INVALID_SIGNAL | UNKNOWN
```

### R-Multiple Formula

For LONG:

```text
risk = entry_price - stop_loss
r_multiple = (exit_price - entry_price) / risk
```

For SHORT:

```text
risk = stop_loss - entry_price
r_multiple = (entry_price - exit_price) / risk
```

Rules:

- If risk <= 0, reject outcome update with `400 INVALID_OUTCOME_VALUES`.
- If `close_reason == TP_HIT`, `is_win = true`.
- If `close_reason == SL_HIT`, `is_win = false`.
- For manual close, derive `is_win = r_multiple > 0` unless explicitly provided.

### Acceptance Criteria

- Migration is idempotent.
- ORM model includes new fields.
- Existing tests still pass.

---

## B2. Outcome Repository

### Goal

Encapsulate outcome DB access.

### Scope

Files:

- `app/repositories/outcome_repo.py`
- `tests/integration/test_outcome_repository.py`

### Methods

```text
OutcomeRepository methods:
- find_by_signal_row_id(signal_row_id: str) -> SignalOutcome | None
- find_by_signal_id(signal_id: str) -> SignalOutcome | None
- create_open_from_signal(signal: Signal) -> SignalOutcome
- upsert_closed_outcome(signal: Signal, exit_price: float, closed_at: datetime, close_reason: str, max_favorable_price: float | None = None, max_adverse_price: float | None = None, notes: str | None = None) -> SignalOutcome
- list_recent(days: int, limit: int) -> list[SignalOutcome]
```

### Behavior

- `create_open_from_signal()` copies entry/SL/TP from signal.
- `upsert_closed_outcome()` computes PnL fields and overwrites existing OPEN outcome.
- Use SQLAlchemy `select()` only.
- Generate UUID in Python.

### Acceptance Criteria

- Repository can create OPEN outcome for a PASS signal.
- Repository can close outcome and compute `r_multiple`.
- Duplicate close update updates same outcome row, not insert duplicate.

---

## B3. Outcome API

### Goal

Admin can record paper trading outcomes manually.

### Scope

Files:

- `app/api/outcome_controller.py`
- `app/main.py`
- `app/domain/schemas.py`
- `app/repositories/outcome_repo.py`
- `tests/integration/test_outcome_api.py`
- `docs/API_REFERENCE.md`

### Endpoints

```http
POST /api/v1/signals/{signal_id}/outcome/open
PUT  /api/v1/signals/{signal_id}/outcome
GET  /api/v1/signals/{signal_id}/outcome
GET  /api/v1/outcomes/recent?days=30&limit=100
```

All endpoints require dashboard/admin auth.

### Request: Open Outcome

No body required, or optional notes:

```json
{"notes":"paper tracking started"}
```

Behavior:

- Signal must exist.
- If outcome exists, return existing outcome with `200`.
- If no outcome, create `OPEN`.

### Request: Close/Update Outcome

```json
{
  "exit_price": 68740.0,
  "closed_at": "2026-04-30T10:15:00Z",
  "close_reason": "TP_HIT",
  "max_favorable_price": 68800.0,
  "max_adverse_price": 68100.0,
  "notes": "TP touched on Binance mark price"
}
```

### Response

```json
{
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "outcome_status": "CLOSED",
  "close_reason": "TP_HIT",
  "is_win": true,
  "entry_price": 68250.5,
  "exit_price": 68740.0,
  "pnl_pct": 0.7172,
  "r_multiple": 1.81,
  "mfe_pct": 0.8051,
  "mae_pct": -0.2205,
  "opened_at": "2026-04-30T09:55:00Z",
  "closed_at": "2026-04-30T10:15:00Z"
}
```

### Validation

- Unknown signal -> `404 SIGNAL_NOT_FOUND`.
- Invalid close_reason -> `400 INVALID_CLOSE_REASON`.
- Invalid price/risk math -> `400 INVALID_OUTCOME_VALUES`.
- Cannot close REJECT signal unless `allow_reject_outcome=true` query param is provided.

### Acceptance Criteria

- Admin auth required.
- Create/open is idempotent.
- Close computes `pnl_pct`, `r_multiple`, `is_win` correctly for LONG and SHORT.
- GET signal detail should include outcome if available.

---

## B4. Auto-Create OPEN Outcome for Pass Signals

### Goal

Optionally create OPEN outcome automatically for signals routed to MAIN/WARN.

### Scope

Files:

- `app/services/webhook_ingestion_service.py`
- `app/repositories/config_repo.py`
- `app/repositories/outcome_repo.py`
- `tests/integration/test_webhook_endpoint.py`

### Config

Add to `signal_bot_config`:

```json
{
  "auto_create_open_outcomes": false
}
```

Default: `false` for backward compatibility.

### Behavior

If config is true and decision is `PASS_MAIN` or `PASS_WARNING`:

- Create `signal_outcomes` row with `outcome_status=OPEN` in same business transaction before commit.
- Do not create outcome for `REJECT` unless future config says so.
- Idempotency still prevents duplicate signal/outcome.

### Acceptance Criteria

- With config false, no outcome auto-created.
- With config true, PASS signal creates one OPEN outcome.
- Duplicate webhook does not create second outcome.

---

# Phase C — Outcome Analytics and Dashboard

## C1. Outcome Analytics Endpoints

### Goal

Measure actual paper trading performance.

### Scope

Files:

- `app/api/analytics_controller.py`
- `app/domain/schemas.py`
- `tests/integration/test_analytics_outcomes.py`
- `docs/API_REFERENCE.md`

### Endpoints

```http
GET /api/v1/analytics/outcomes/summary?days=30
GET /api/v1/analytics/outcomes/by-bucket?days=30&group_by=timeframe,signal_type
GET /api/v1/analytics/outcomes/rules?days=30
```

All require dashboard auth.

### Summary Response

```json
{
  "period_days": 30,
  "closed_outcomes": 42,
  "open_outcomes": 8,
  "win_rate": 0.5714,
  "avg_r_multiple": 0.42,
  "median_r_multiple": 0.25,
  "total_r_multiple": 17.64,
  "avg_pnl_pct": 0.31,
  "by_decision": {
    "PASS_MAIN": {"count": 20, "win_rate": 0.65, "avg_r": 0.7},
    "PASS_WARNING": {"count": 22, "win_rate": 0.50, "avg_r": 0.17}
  }
}
```

### Bucket Rules

Allowed `group_by` values:

```text
timeframe, signal_type, strategy, side, decision, telegram_route, regime, vol_regime, reject_code
```

Reject unknown group value with `400 INVALID_GROUP_BY`.

### Rule Analytics

For each filter rule:

```json
{
  "rule_code": "LOW_VOLUME_WARNING",
  "result": "WARN",
  "severity": "MEDIUM",
  "signals": 12,
  "closed_outcomes": 8,
  "win_rate": 0.375,
  "avg_r_multiple": -0.15
}
```

### Acceptance Criteria

- Empty data returns zeros, not 500.
- Only CLOSED outcomes count toward win rate/avg R.
- OPEN outcomes count separately.
- Query uses `select()` and does not load all rows unnecessarily.

---

## C2. Dashboard V1.2 Trading Ops Command Center

### Goal

Turn `/dashboard` from a basic analytics page into a Trading Ops Command Center: a polished operations cockpit for monitoring webhook health, Telegram delivery, paper outcomes, signal quality, and calibration risks in one responsive interface.

### Product Direction

Use the confirmed **Trading Ops Command Center** direction, not a generic chart dashboard.

Dashboard V1.2 should answer these operator questions within 10 seconds:

1. Is the bot healthy right now?
2. Did TradingView send a recent webhook?
3. Are Telegram notifications being delivered?
4. Are MAIN signals outperforming WARN signals?
5. Which timeframe/strategy/rule needs attention?
6. Is paper trading performance improving or degrading?

### Scope

Files:

- `app/templates/dashboard.html`
- `app/api/analytics_controller.py`
- `app/api/health_controller.py`
- `app/domain/schemas.py`
- `tests/integration/test_dashboard_auth.py`
- `tests/integration/test_analytics.py`
- `tests/integration/test_analytics_outcomes.py`
- `docs/API_REFERENCE.md`

### Visual Direction

Design language:

- Style: high-signal operations cockpit, dark command center, data-dense but calm.
- Avoid: generic admin template, default Bootstrap look, purple-heavy AI-style layout.
- Typography: replace current generic Inter-only direction with an intentional pairing:
  - headings: `Space Grotesk` or `Sora`
  - numbers/data: `JetBrains Mono` or `IBM Plex Mono`
  - body: `Manrope` or `Source Sans 3`
- Background: layered dark surface with subtle grid/noise/radial gradients, not flat black.
- Color tokens:
  - MAIN / healthy: green-cyan
  - WARN / attention: amber
  - REJECT / failure: red-coral
  - ADMIN / ops: steel-blue
  - neutral analytics: slate
- Motion: subtle load-in and pulse only for live/alert states; no distracting animations.

Required CSS token groups:

```text
--surface-base
--surface-panel
--surface-raised
--border-soft
--text-strong
--text-muted
--route-main
--route-warn
--route-reject
--route-admin
--health-ok
--health-warn
--health-fail
--risk-low
--risk-medium
--risk-high
```

### Information Architecture

Use a 12-column desktop grid and stacked mobile layout.

```text
Desktop layout:
┌──────────────────────────────────────────────────────────────┐
│ Command Header: status pills, range selector, refresh         │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ Ops Snapshot │ Delivery     │ Outcomes     │ Active Alerts  │
├──────────────────────────────┬───────────────────────────────┤
│ Signal Radar / Timeline      │ Risk & Reliability Panel       │
├──────────────────────────────┴───────────────────────────────┤
│ Performance Intelligence: charts + rule performance           │
├──────────────────────────────────────────────────────────────┤
│ Recent Outcomes / Export / Calibration Insights               │
└──────────────────────────────────────────────────────────────┘
```

Mobile layout:

```text
Header -> health strip -> metric cards -> alert cards -> signal feed -> charts -> outcomes table
```

### Required UI Modules

#### 1. Command Header

Show:

- product name: `Signal Bot Command Center`
- environment and app version
- active config version
- range selector: `24h`, `7d`, `30d`, `90d`
- manual refresh button
- last refreshed timestamp
- compact health pills:
  - API
  - DB
  - Config
  - Telegram
  - Webhook freshness

Health pill states:

```text
OK      -> green
WARN    -> amber
FAIL    -> red
UNKNOWN -> muted slate
```

#### 2. Ops Snapshot Cards

Cards:

- Total signals
- PASS_MAIN count and percentage
- PASS_WARNING count and percentage
- REJECT count and percentage
- Telegram sent rate
- Telegram failed count
- Open outcomes
- Closed outcomes
- Win rate
- Avg R
- Total R

Each card must include:

- label
- primary value
- small supporting text
- trend indicator if previous period data is available
- empty state if value is unavailable

#### 3. Signal Radar

Timeline feed optimized for fast scanning.

Each row/card shows:

```text
created_at | route badge | side | symbol | timeframe | signal_type | strategy | entry | RR | confidence | decision reason
```

Badges:

- `MAIN`
- `WARN`
- `REJECT`
- `ADMIN`
- `DUPLICATE` if included in future feed

Quick filters:

- decision
- route
- side
- timeframe
- signal_type
- strategy
- only warnings
- only rejects

UX behavior:

- Filters apply client-side for loaded rows.
- Selected filters persist in query string or localStorage.
- Empty state explains whether no data exists or filters hide all rows.
- Clicking a row expands rule details if data is available from existing signal detail endpoint.

#### 4. Performance Intelligence

Charts/tables:

- Main vs Warn performance: win rate, avg R, total R.
- Win rate by timeframe.
- Avg R by signal_type.
- Outcome daily line chart.
- Rule performance table with win rate and avg R.
- Reject code distribution.

Use Chart.js already present in the current dashboard. Do not introduce a new frontend framework in V1.2.

#### 5. Risk & Reliability Panel

Show operational alerts:

```text
STALE_WEBHOOK          Last webhook older than configured threshold
TELEGRAM_FAIL_SPIKE    Failed delivery rate above threshold
INVALID_SECRET_SPIKE   Invalid auth count above threshold
INVALID_SCHEMA_SPIKE   Invalid payload/schema count above threshold
DUPLICATE_SPIKE        Duplicate count above threshold
REJECT_SPIKE           Reject rate above threshold
CONFIG_DRIFT           Reverify changed-decision rate above threshold
```

Each alert includes:

- severity: LOW | MEDIUM | HIGH
- metric value
- threshold
- suggested operator action
- link/filter target if available

#### 6. Recent Outcomes

Table columns:

```text
signal_id | decision | route | side | tf | signal_type | close_reason | R | pnl_pct | closed_at
```

UX:

- Color positive R green, negative R red, zero muted.
- Show OPEN outcomes separately from CLOSED outcomes.
- Include export CSV shortcut.

#### 7. Calibration Insights

Show advisory-only recommendations from calibration report:

```text
bucket | samples | win_rate | avg_r | recommendation | confidence
```

Requirements:

- Must clearly label as `Advisory only`.
- Must not allow config changes directly in Dashboard V1.2 unless Config Admin API is already implemented.
- If samples < minimum, show `INSUFFICIENT_DATA` instead of recommendation.

### API Additions for Dashboard

Add one aggregation endpoint to avoid excessive client requests:

```http
GET /api/v1/analytics/ops-command-center?days=7
```

Response shape:

```json
{
  "period_days": 7,
  "generated_at": "2026-04-30T12:00:00Z",
  "health": {
    "api": "OK",
    "database": "OK",
    "config": "OK",
    "telegram": "UNKNOWN",
    "webhook_freshness": "WARN",
    "last_webhook_at": "2026-04-30T11:42:00Z",
    "config_version": 3
  },
  "ops_snapshot": {
    "total_signals": 128,
    "pass_main": 52,
    "pass_warning": 31,
    "reject": 45,
    "telegram_sent_rate": 0.97,
    "telegram_failed": 2,
    "open_outcomes": 11,
    "closed_outcomes": 42,
    "win_rate": 0.5714,
    "avg_r": 0.42,
    "total_r": 17.64
  },
  "alerts": [
    {
      "code": "STALE_WEBHOOK",
      "severity": "MEDIUM",
      "value": 38,
      "threshold": 30,
      "message": "Last webhook was 38 minutes ago",
      "action": "Check TradingView alert status"
    }
  ],
  "performance": {
    "main_vs_warn": [],
    "by_timeframe": [],
    "by_signal_type": [],
    "rule_performance": []
  },
  "recent_signals": [],
  "recent_outcomes": [],
  "calibration_insights": []
}
```

Rules:

- `days` allowed range: 1-90.
- Endpoint requires dashboard auth.
- Empty datasets return empty arrays/zero values, not 500.
- Health check inside this endpoint must not send Telegram messages.

### Frontend Implementation Constraints

- Keep single-file dashboard for V1.2 unless it becomes too large; if splitting, use `app/static/dashboard.css` and `app/static/dashboard.js` only.
- Do not introduce React/Vue/Svelte in V1.2.
- Keep Chart.js unless there is a strong reason to change.
- Dashboard must work without build tooling.
- All API calls include existing dashboard token behavior.
- No secret values are rendered into charts, tables, logs, or error messages.

### Loading, Empty, and Error States

Required states:

- Initial skeleton loading for cards and chart panels.
- Empty state for no signals/outcomes.
- Filter-empty state for filters hiding all data.
- API error banner with retry button.
- Auth error redirects or shows clear unauthorized state.
- Stale data warning if refresh fails but old data remains visible.

### Accessibility and Responsiveness

Requirements:

- Desktop: optimized for 1440px width.
- Tablet: cards wrap cleanly at 768px.
- Mobile: single-column layout at 390px width.
- Route/health states cannot rely only on color; include text labels/icons.
- Tables must be horizontally scrollable on mobile.
- Interactive controls have visible focus states.
- Chart panels have text summary fallback.

### Acceptance Criteria

- Dashboard loads on desktop and mobile.
- Dashboard visually reads as an intentional command center, not a generic admin page.
- Existing dashboard auth remains required.
- No token appears in API logs.
- Existing signal summary remains available.
- Outcome summary, signal radar, risk alerts, and performance intelligence render empty states without errors.
- `GET /api/v1/analytics/ops-command-center?days=7` requires auth and returns stable response keys.
- The dashboard does not send Telegram messages or mutate business data.
- Existing dashboard tests still pass.

---

## C3. CSV Export for Paper Review

### Goal

Export data để phân tích ngoài app.

### Scope

Files:

- `app/api/analytics_controller.py`
- `tests/integration/test_analytics_export.py`

### Endpoint

```http
GET /api/v1/analytics/export/outcomes.csv?days=90
```

Columns:

```csv
signal_id,created_at,closed_at,symbol,timeframe,side,signal_type,strategy,decision,telegram_route,entry_price,stop_loss,take_profit,exit_price,close_reason,is_win,pnl_pct,r_multiple,regime,vol_regime,indicator_confidence,server_score,failed_rules,warn_rules
```

### Acceptance Criteria

- Requires dashboard auth.
- Returns `text/csv`.
- Escapes CSV safely.
- Supports empty result with header only.

---

# Phase D — Replay, Reverify, and Calibration

## D1. Batch Reverify Endpoint

### Goal

Replay current filter config against many historical signals without mutating original decisions.

### Scope

Files:

- `app/api/signal_controller.py`
- `app/repositories/reverify_repo.py`
- `tests/integration/test_signal_reverify.py`
- `docs/API_REFERENCE.md`

### Endpoint

```http
POST /api/v1/signals/reverify/batch
```

Request:

```json
{
  "days": 30,
  "limit": 500,
  "decision": ["PASS_MAIN", "PASS_WARNING", "REJECT"],
  "signal_type": ["LONG_V73", "SHORT_V73", "SHORT_SQUEEZE"],
  "persist_results": true
}
```

Response:

```json
{
  "requested": 500,
  "processed": 123,
  "changed_decisions": 7,
  "summary": {
    "PASS_MAIN->PASS_WARNING": 3,
    "PASS_WARNING->REJECT": 2,
    "REJECT->PASS_WARNING": 2
  },
  "results": [
    {
      "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
      "original_decision": "PASS_MAIN",
      "reverify_decision": "PASS_WARNING",
      "changed": true,
      "decision_reason": "Warnings triggered: BACKEND_SCORE_THRESHOLD"
    }
  ]
}
```

### Safety

- Does not update `signals`, `signal_decisions`, or `telegram_messages`.
- If `persist_results=true`, writes only to `signal_reverify_results`.
- Limit max 1000 per request.

### Acceptance Criteria

- Requires admin auth.
- Handles legacy rows with missing optional strategy metadata.
- Never sends Telegram.

---

## D2. Offline Replay CLI

### Goal

Replay JSON payload files locally without hitting Telegram.

### Scope

Files:

- `scripts/replay_payloads.py`
- `docs/LOCAL_SMOKE_CHECKLIST.md`
- `tests/unit/test_replay_payloads.py` or integration test if DB-backed

### Command

```bash
python scripts/replay_payloads.py --input docs/examples/v11_sample_payloads --output /tmp/replay_results.jsonl
```

Options:

```text
--input FILE_OR_DIR
--output FILE
--config-db-key signal_bot_config
--dry-run true
--persist false
```

### Behavior

- Loads payload JSON files.
- Validates with `TradingViewWebhookPayload`.
- Normalizes and runs `FilterEngine`.
- Does not send Telegram.
- If `persist=false`, does not write DB.
- Writes JSONL result per payload.

### Acceptance Criteria

- Sample payloads replay without error.
- Invalid payloads produce structured error result.
- No Telegram dependency required.

---

## D3. Calibration Report

### Goal

Suggest rule/config changes from outcomes without auto-applying them.

### Scope

Files:

- `app/services/calibration_report.py`
- `app/api/analytics_controller.py`
- `tests/unit/test_calibration_report.py`
- `tests/integration/test_calibration_api.py`

### Endpoint

```http
GET /api/v1/analytics/calibration/report?days=90&min_samples=30
```

### Report Sections

1. Sample health:

```json
{"closed_outcomes":120,"min_samples":30,"eligible_buckets":5,"insufficient_buckets":8}
```

2. Bucket performance:

```json
{
  "bucket": {"timeframe":"5m","signal_type":"LONG_V73"},
  "samples": 42,
  "win_rate": 0.61,
  "avg_r": 0.48,
  "recommendation": "KEEP"
}
```

3. Rule impact:

```json
{
  "rule_code": "LOW_VOLUME_WARNING",
  "result": "WARN",
  "samples": 35,
  "avg_r": -0.22,
  "recommendation": "REVIEW_TIGHTEN"
}
```

4. Threshold suggestions:

```json
{
  "config_key": "confidence_thresholds.5m",
  "current": 0.78,
  "suggested": 0.80,
  "reason": "Signals below 0.80 show negative avg R over 37 closed outcomes",
  "confidence": "LOW"
}
```

### Rules

- Do not generate threshold suggestion for bucket with samples < `min_samples`.
- Recommendation labels only:

```text
KEEP | WATCH | REVIEW_TIGHTEN | REVIEW_RELAX | INSUFFICIENT_DATA
```

- Report is advisory only; no DB config update.

### Acceptance Criteria

- Empty/low sample returns `INSUFFICIENT_DATA`.
- No config mutation.
- Tests cover sample size guard.

---

# Phase E — Config Audit and Market Context

## E1. Config Versioning and Audit Log

### Goal

Mọi thay đổi config có history và mỗi signal biết config version đã dùng.

### Scope

Files:

- `migrations/008_v12_config_audit.sql`
- `app/domain/models.py`
- `app/repositories/config_repo.py`
- `app/services/webhook_ingestion_service.py`
- `tests/integration/test_config_audit.py`

### Schema

```sql
CREATE TABLE IF NOT EXISTS system_config_audit_logs (
    id UUID PRIMARY KEY,
    config_key VARCHAR(128) NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by VARCHAR(128),
    change_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE system_configs ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS config_version INTEGER;
```

### Repository Methods

```text
ConfigRepository methods:
- get_signal_bot_config_with_version() -> tuple[dict, int]
- update_config_with_audit(config_key: str, new_value: dict, changed_by: str, change_reason: str) -> SystemConfig
```

### Behavior

- Webhook ingestion stores config version on `signals.config_version`.
- Updating config increments version.
- Audit log stores old and new JSON.

### Acceptance Criteria

- Config update writes audit row.
- Signal created after config update stores new version.
- Existing signals can have null `config_version`.

---

## E2. Config Admin API

### Goal

Admin can view config and audit logs safely. Editing can be added but must be guarded.

### Scope

Files:

- `app/api/config_controller.py`
- `app/main.py`
- `tests/integration/test_config_api.py`
- `docs/API_REFERENCE.md`

### Endpoints

```http
GET /api/v1/admin/config/signal-bot
GET /api/v1/admin/config/audit-log?limit=50
PUT /api/v1/admin/config/signal-bot
```

### PUT Request

```json
{
  "config_value": {"confidence_thresholds":{"5m":0.80}},
  "change_reason": "Raise 5m threshold after 90d calibration report"
}
```

### Safety

- Requires dashboard/admin auth.
- Deep merge partial config with defaults/current config.
- Validate required keys before saving.
- Reject if `change_reason` missing or shorter than 10 chars.
- Never log secret values.

### Acceptance Criteria

- GET returns config without secrets.
- PUT partial update preserves other nested config keys.
- PUT writes audit log and increments version.

---

## E3. Independent Market Context Design Slice

### Goal

Bắt đầu giảm circular dependency từ payload `regime`/`vol_regime`.

### Scope

Files:

- `app/services/market_context_service.py`
- `app/repositories/market_context_repo.py`
- `migrations/009_v12_market_context.sql`
- `tests/unit/test_market_context_service.py`

### Schema

```sql
CREATE TABLE IF NOT EXISTS market_context_snapshots (
    id UUID PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    timeframe VARCHAR(16) NOT NULL,
    bar_time TIMESTAMP NOT NULL,
    backend_regime VARCHAR(64),
    backend_vol_regime VARCHAR(64),
    ema_fast NUMERIC(18,8),
    ema_mid NUMERIC(18,8),
    ema_slow NUMERIC(18,8),
    atr_pct NUMERIC(10,6),
    volume_ratio NUMERIC(10,4),
    source VARCHAR(64) NOT NULL,
    raw_context JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, timeframe, bar_time, source)
);
```

### V1.2 Slice Behavior

- No external network dependency required initially.
- Service can compute/compare context if snapshot exists.
- Filter rule added as WARN only:

```text
BACKEND_REGIME_MISMATCH
payload regime != backend_regime -> WARN MEDIUM
```

- Rule is enabled by config:

```json
{"enable_backend_regime_compare": false}
```

Default: `false`.

### Acceptance Criteria

- With config false, no new filter result.
- With config true and matching snapshot, PASS.
- With mismatch, WARN MEDIUM -> route can become PASS_WARNING.
- No webhook failure if snapshot missing; add PASS/SKIP-like result or no-op by design.

---

# 5. Cross-Cutting Test Plan

## Required test categories

### Unit

- Outcome math LONG/SHORT.
- Telegram retry policy.
- Calibration sample guard.
- Config deep merge/audit validation.
- Market context comparison.

### Integration

- Webhook still persists before notify.
- Duplicate `signal_id` still returns `DUPLICATE` and does not create outcome twice.
- Outcome API auth + validation.
- Analytics outcome endpoints empty and non-empty.
- Ops Command Center aggregation endpoint auth, empty-state shape, and stable response keys.
- Dashboard auth still protects `/dashboard` and all dashboard API calls.
- Batch reverify does not mutate original decisions.
- Health readiness DB failure path.

### Regression invariants

Add or preserve tests for:

```text
- Invalid JSON creates webhook_event.
- Invalid secret creates webhook_event but no signal.
- Telegram failure does not fail webhook response.
- FAIL rule always REJECT.
- WARN MEDIUM+ always PASS_WARNING.
- server_score is not used as pass/reject gate.
- No app code uses db.query().
- rg "Optional\[" app returns no result.
```

## Standard verify commands

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest -q
bash scripts/smoke_local.sh
```

---

# 6. Migration Plan

Recommended migration files:

```text
006_v12_observability.sql
007_v12_signal_outcomes.sql
008_v12_config_audit.sql
009_v12_market_context.sql
```

Migration requirements:

- Raw SQL only, no Alembic.
- Idempotent with `IF NOT EXISTS` or guarded DDL.
- Do not drop or rewrite existing data.
- Backward compatible with existing rows.
- Update `docs/DB_MIGRATION_RUNBOOK.md` if migration flow changes.

Verification:

```bash
python scripts/db/migrate.py
python -m pytest tests/integration/test_ci_migration_fixture.py -q
```

---

# 7. API Error Contract

New V1.2 errors should follow existing `ErrorResponse` shape.

Recommended error codes:

```text
SIGNAL_NOT_FOUND
OUTCOME_NOT_FOUND
INVALID_OUTCOME_VALUES
INVALID_CLOSE_REASON
INVALID_GROUP_BY
CONFIG_VALIDATION_FAILED
CONFIG_REASON_REQUIRED
BATCH_LIMIT_EXCEEDED
DEPENDENCY_UNAVAILABLE
```

Example:

```json
{
  "error_code": "INVALID_OUTCOME_VALUES",
  "message": "Cannot compute R multiple because risk is not positive"
}
```

---

# 8. Security Requirements

- All admin/outcome/config/analytics endpoints require dashboard auth unless already public health endpoint.
- Do not expose Telegram chat IDs in dashboard unless explicitly needed.
- Redact tokens/secrets in logs and DB raw headers.
- CSV export must escape values safely.
- Config API must not allow changing env secrets; only DB `signal_bot_config`.
- PUT config requires `change_reason`.

---

# 9. Performance Requirements

- Webhook response should stay fast; target p95 under 250ms excluding DB cold starts and Telegram background delivery.
- Outcome analytics should aggregate in SQL, not Python loops over all rows.
- Dashboard endpoints should limit lookback to max 90 days unless explicitly expanded.
- `GET /api/v1/analytics/ops-command-center` should aggregate in one SQL-focused service path and avoid N+1 detail calls.
- Dashboard first contentful render should stay fast with skeleton states while charts load asynchronously.
- Batch reverify max 1000 signals per request.
- Duplicate suppression should stay DB-range filtered by entry price.

---

# 10. Definition of Done for V1.2

V1.2 is complete when:

- [ ] Production health endpoints exist and are tested.
- [ ] Correlation ID is stored and logged for webhook pipeline.
- [ ] Telegram notifier has safe retry/connection reuse.
- [ ] Outcome schema/repository/API are implemented.
- [ ] PASS signals can create OPEN outcome optionally by config.
- [ ] CLOSED outcomes compute win/loss, PnL, R multiple for LONG and SHORT.
- [ ] Outcome analytics summary/bucket/rule endpoints exist.
- [ ] Ops Command Center aggregation endpoint exists and is authenticated.
- [ ] Dashboard shows Trading Ops Command Center with health, signal radar, risk alerts, outcome performance, and calibration insights.
- [ ] Dashboard has intentional visual design, responsive layout, loading states, empty states, and error states.
- [ ] CSV export works.
- [ ] Batch reverify exists and does not mutate original decisions.
- [ ] Calibration report exists and is advisory only.
- [ ] Config audit/versioning exists.
- [ ] Full test suite passes.
- [ ] Docs updated: API reference, DB schema, QA strategy, deployment/smoke checklist.

---

# 11. Suggested PR Breakdown

Keep PRs small and mergeable:

1. **PR-01:** Make targets + docs verify cleanup.
2. **PR-02:** Correlation ID + pipeline summary log.
3. **PR-03:** Health readiness/deps endpoints.
4. **PR-04:** Telegram notifier retry/client reuse.
5. **PR-05:** Outcome schema + repository.
6. **PR-06:** Outcome API + signal detail include outcome.
7. **PR-07:** Auto-create OPEN outcome config.
8. **PR-08:** Outcome analytics endpoints.
9. **PR-09:** Dashboard Trading Ops Command Center + ops aggregation endpoint.
10. **PR-10:** CSV export.
11. **PR-11:** Batch reverify endpoint.
12. **PR-12:** Offline replay CLI.
13. **PR-13:** Calibration report.
14. **PR-14:** Config audit/versioning.
15. **PR-15:** Config admin API.
16. **PR-16:** Market context snapshot slice.

---

# 12. Recommended First Sprint

Start with these tasks because they reduce risk for all later work:

```text
Sprint V1.2-A
1. A1 Repository Hygiene and Verify Targets
2. A2 Correlation ID and Pipeline Summary Log
3. A3 Health Readiness Endpoints
4. A4 Telegram Notifier Connection Reuse and Retry
```

Sprint V1.2-A DoD:

- Existing behavior unchanged.
- Full test suite passes.
- Webhook traceability improved.
- Deploy health checks ready.
- Telegram failure still does not affect webhook response.

