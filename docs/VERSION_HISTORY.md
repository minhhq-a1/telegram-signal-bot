# Version History — Telegram Signal Bot

File này là nguồn duy nhất giữ lịch sử phiên bản product-level. Các context hiện hành nên nói V1.3; các phiên bản cũ được giữ ở đây để biết bot đã nâng cấp qua từng giai đoạn như thế nào.

## V1.0 — Baseline Signal Bot

Mục tiêu V1.0 là đưa bot vào trạng thái chạy được end-to-end cho paper trading / production nhẹ.

- Nhận webhook TradingView tại `POST /api/v1/webhooks/tradingview`.
- Audit-first vào `webhook_events`, kể cả invalid JSON/schema/secret.
- Idempotency bằng `signal_id`, duplicate trả `200 DUPLICATE`.
- Normalize payload và persist `signals`.
- Filter Engine boolean gate: `FAIL -> REJECT`, `WARN MEDIUM+ -> PASS_WARNING`, còn lại `PASS_MAIN`.
- `server_score` chỉ lưu analytics, không dùng route.
- Telegram routing `MAIN`, `WARN`, `ADMIN/NONE` theo decision/config.
- DB core tables: `webhook_events`, `signals`, `signal_filter_results`, `signal_decisions`, `telegram_messages`, `system_configs`, `market_events`, `signal_outcomes`.

## V1.1 — Strategy Validation, Reverify, Analytics

V1.1 giữ nguyên nguyên tắc V1.0 nhưng bổ sung rule/ops layer để debug và đánh giá signal tốt hơn.

- Thêm timeframe runtime whitelist `30m`, `1h` cùng threshold/cooldown tương ứng.
- Thêm strategy-specific validation cho `SHORT_SQUEEZE`, `SHORT_V73`, `LONG_V73`.
- Thêm quality floor WARN rules, `RR_PROFILE_MATCH`, và backend rescoring pilot (`BACKEND_SCORE_THRESHOLD` là WARN, không FAIL).
- Thêm `mom_direction`, `strategy_thresholds`, `rr_target_by_type`, `rescoring`, `score_pass_threshold` trong config/migration.
- Thêm `signal_reverify_results` và endpoint `POST /api/v1/signals/{id}/reverify`.
- Thêm `GET /api/v1/signals/{id}/reverify-results`.
- Thêm analytics/reject-stats, dashboard auth, và webhook rate limiting.
- Webhook notification flow được chuẩn hóa: commit business records trước, Telegram delivery chạy background và log `telegram_messages` bằng session riêng.

## V1.2 — Config Audit, Market Context Foundation

V1.2 thêm config versioning và market context snapshot infrastructure.

- Config audit trail: `system_config_audit_log` table tracks all config changes with old/new values.
- Config versioning: `system_configs.version` increments on each update.
- Market context snapshots: `market_context_snapshots` table stores backend regime/volatility data.
- Dashboard improvements: Command Center panel, config history view.
- Migration 008: Config audit log schema.
- Migration 009: Market context snapshots schema.

## V1.3 — Decision Intelligence & Controlled Calibration

**Released:** 2026-05-04

V1.3 adds calibration proposals, config dry-run/rollback, replay comparison, market context advisory filtering, and dashboard decision intelligence panel.

### Service Boundaries & Refactoring

- **Filter Engine refactor:** Extracted filter rules into focused modules (`app/services/filter_rules/`):
  - `types.py`: Shared `FilterResult` and `FilterExecutionResult` types
  - `validation.py`: Symbol, timeframe, confidence, price validation
  - `trade_math.py`: Direction sanity and RR checks
  - `business.py`: Confidence threshold, duplicate, news block, regime hard block
  - `advisory.py`: Volatility, cooldown, low volume, RR profile, backend score warnings
  - `routing.py`: Boolean gate decision logic
  - `market_context.py`: Market context regime mismatch adapter
- **Config validation service:** Pydantic v2 validation for `signal_bot_config` with strict write-path validation and warning-only read-path validation for legacy compatibility.
- **Calibration service:** Extracted calibration report assembly from controller into `calibration_report.py`.
- **Replay service:** Reusable replay and compare engine in `replay_service.py`.

### Market Context Advisory

- **New filter rule:** `BACKEND_REGIME_MISMATCH` (group: `market_context`, severity: `MEDIUM`)
  - Compares payload regime with backend market context snapshot
  - Advisory mode: returns `WARN` on mismatch, never `FAIL`
  - Tolerant lookup: finds most recent snapshot at or before `bar_time` within configurable window (default 10 minutes)
  - Config: `market_context.enabled`, `market_context.regime_mismatch_mode`, `market_context.snapshot_max_age_minutes`
- **New index:** `idx_market_context_symbol_tf_source_bar_time` for efficient snapshot lookup (migration 010)
- **Repository:** `MarketContextRepository.find_snapshot()` uses asymmetric window (at-or-before-close semantics)

### Calibration Proposals

- **New endpoint:** `GET /api/v1/analytics/calibration/proposals`
  - Analyzes closed signal outcomes over configurable period (default 90 days)
  - Generates confidence threshold adjustment proposals based on win rate and avg R multiple
  - Proposals clamped to max step ±0.03 from current value
  - Returns proposal ID, current/suggested values, direction (TIGHTEN/RELAX), confidence level, sample health
  - Requires dashboard auth token
- **Service:** `calibration_proposals.py` builds proposals from calibration report and live config

### Config Management

- **Dry-run endpoint:** `POST /api/v1/admin/config/signal-bot/dry-run`
  - Validates config changes before applying
  - Returns changed paths, merged config, validation warnings
  - Requires `change_reason` (min 10 chars)
  - Does not mutate live config
- **Rollback endpoint:** `POST /api/v1/admin/config/signal-bot/rollback`
  - Rolls back to previous config version
  - Reconstructs historical config by scanning audit logs backward
  - Creates new version (does not overwrite history)
  - Requires `target_version` and `change_reason`
- **Repository:** `ConfigRepository.get_config_value_by_version()` and `diff_config_paths()` helpers

### Replay Improvements

- **Compare mode:** `scripts/replay_payloads.py --input <path> --output <path> --compare-config-file <path>`
  - Compares current config vs proposed config on same payload set
  - Requires `--input` (payload file or directory), `--output` (JSONL output file), and `--compare-config-file` (proposed config JSON)
  - Returns decision changes, route changes, changed rule codes
  - Summary output: total, changed decisions, main→warn, pass→reject, reject→pass
- **Config file support:** `--config-file` argument for using custom config instead of default

### Dashboard

- **Decision Intelligence panel:** Displays calibration proposals with current→suggested values, direction, confidence, and reason
- **Proposal rendering:** Shows config path, threshold change, sample health metrics
- **Auth:** All new analytics/config endpoints require dashboard token

### Migrations

- **010_v13_market_context_index.sql:** Market context snapshot lookup index

### Config Schema Changes

- **New config section:** `market_context`
  - `enabled`: boolean (default: false)
  - `regime_mismatch_mode`: "WARN" (default)
  - `snapshot_max_age_minutes`: int (default: 10, range: 1-1440)
- **Validation:** Pydantic v2 models enforce schema, reject unknown keys, validate ranges

### API Changes

- **New endpoints:**
  - `GET /api/v1/analytics/calibration/proposals` (auth required)
  - `POST /api/v1/admin/config/signal-bot/dry-run` (auth required)
  - `POST /api/v1/admin/config/signal-bot/rollback` (auth required)
- **Auth:** Dashboard token via `Authorization: Bearer <token>` header

### Testing

- Unit tests: 182 passing (filter rules, config validation, calibration proposals, replay service)
- Integration tests: Config dry-run/rollback, market context lookup, calibration proposals API
- Migration tests: Verified migration 010 applies cleanly

### Known Limitations

- Market context advisory mode only: `BACKEND_REGIME_MISMATCH` returns `WARN`, not `FAIL`
- Rollback uses audit log scan (no dedicated version columns in V1.3)
- Calibration proposals limited to confidence thresholds (no RR or cooldown proposals yet)
- Replay compare mode CLI-only (no dashboard UI)

### Upgrade Notes

- Run migration 010 before deploying V1.3
- Market context filtering disabled by default (`market_context.enabled: false`)
- Config validation strict on writes, warning-only on reads (preserves legacy compatibility)
- New dashboard endpoints require `DASHBOARD_TOKEN` env var



## Deferred Beyond V1.3

- Auto-trading, position sizing, position-state risk gate.
- SOFT_PASS decision type.
- User profile aggressive/conservative mode.
- Independent exchange market data source cho HTF/regime validation.
- Redis/distributed rate limiting nếu deploy nhiều instances.
