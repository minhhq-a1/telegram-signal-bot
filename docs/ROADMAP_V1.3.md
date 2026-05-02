# ROADMAP V1.3 - Decision Intelligence & Controlled Calibration
<!--
  Roadmap executable cho Telegram Signal Bot sau V1.2.1.
  Muc tieu: bien outcome data, replay, calibration va market context thanh mot workflow
  review config co kiem soat. Khong auto-trade trong V1.3.
-->

## 0. Executive Summary

V1.2.1 da dua bot vao trang thai production-usable cho paper trading:

- webhook audit/idempotency/filter/notify da on dinh hon;
- outcome API va outcome analytics da co;
- dashboard da thanh Trading Ops Command Center;
- batch reverify, offline replay CLI, calibration report va config audit da co nen tang;
- market context snapshot store da co slice dau tien.

V1.3 nen tap trung vao **Decision Intelligence**: dung du lieu that de de xuat thay doi filter/config, nhung van bat buoc review thu cong va replay truoc khi apply.

North Star Metric cho V1.3:

```text
Moi thay doi filter/config co the trace day du:
outcome data -> calibration insight -> proposed config diff -> replay impact -> reviewed config change -> audited config version
```

V1.3 tiep tuc **khong auto-trade** va khong tu dong apply calibration vao live routing.

---

## 1. Non-Negotiable Invariants

Moi task V1.3 phai giu cac rule hien co:

1. **Persist before notify** - khong gui Telegram truoc khi commit business records.
2. **Idempotency** - `signal_id` da ton tai tra `200 DUPLICATE`, khong insert lai.
3. **Audit-first** - moi webhook deu log vao `webhook_events`, ke ca invalid.
4. **DB config first** - threshold/cooldown/ops config doc tu `system_configs`.
5. **No secret logging** - khong log TradingView secret, Telegram token, dashboard token, auth headers.
6. **Boolean gate routing** - route theo FAIL/WARN, khong theo `server_score >= threshold`.
7. **SQLAlchemy 2.0 style** - dung `select()`, khong dung `db.query()` trong `app/`.
8. **Python 3.12 typing** - dung `str | None`, khong dung `Optional[str]`.
9. **UTC timestamps** - dung `datetime.now(timezone.utc)`.
10. **Python UUID generation** - dung `str(uuid.uuid4())` o Python layer.
11. **No auto-trade** - V1.3 chi lam decision support, paper analytics, admin tooling.
12. **Manual calibration approval** - calibration chi de xuat; config live chi doi sau admin review/apply co audit.

---

## 2. Current State Snapshot

### Da co tren `main` V1.2.1

- `WebhookIngestionService` da co correlation ID, pipeline summary log, persist-before-notify.
- `FilterEngine` van la boolean gate, co strategy validation va backend rescoring WARN pilot.
- `signal_outcomes` da co open/close API, outcome math va analytics.
- Dashboard `/dashboard` da co ops snapshot, recent signals/outcomes, performance va calibration insight placeholder.
- `signal_reverify_results` va batch reverify endpoint da co.
- `scripts/replay_payloads.py` da replay payload JSON qua normalizer + filter engine va xuat JSONL.
- `system_configs` da co version/audit va admin config API.
- `market_context_snapshots` va `MarketContextService.compare_regime()` da co slice nen tang.

### Khoang trong chinh

- `MarketContextService` chua duoc cam vao production filter path.
- `BACKEND_REGIME_MISMATCH` moi co service/test rieng, chua persist thanh filter result khi ingest webhook.
- Calibration report moi o muc advisory don gian, chua tao config proposal co diff/impact.
- Replay CLI co tham so `--config-db-key`, `--persist`, `--dry-run` nhung chua that su ho tro DB-backed config, compare config, hay persist.
- Config admin API apply raw patch, chua co proposal/dry-run/rollback workflow.
- Dashboard calibration section moi hien insight gon, chua cho thay replay impact hay config diff.
- `FilterEngine` va `analytics_controller.py` dang co xu huong phinh to; V1.3 them rule/proposal moi nen can tach boundary som.
- Config update hien deep-merge raw dict linh hoat, chua co validation schema du manh cho dry-run/apply/rollback.

---

## 3. V1.3 Scope

### In scope

- Cam market context vao filter pipeline theo config flag.
- Tach `FilterEngine` thanh rule modules nho hon ma giu public API `run()` hien tai.
- Them validation layer cho `signal_bot_config` truoc dry-run/apply.
- Tach calibration aggregation/proposal logic khoi controller thanh service rieng.
- Tach replay logic khoi CLI thanh service dung chung.
- Nang calibration thanh proposal engine co sample guard va config diff.
- Them config dry-run/apply workflow co audit va rollback-friendly versioning.
- Nang replay CLI thanh tool compare before/after config.
- Toi uu market context query/index cho nearest snapshot lookup.
- Dashboard hien calibration proposal, replay impact va market-context health.
- Cap nhat docs/API/schema/test matrix cho V1.3.

### Out of scope

- Auto-trading, broker execution, position sizing live.
- ML model training/live model routing.
- Tu dong apply config vao production khong qua admin review.
- Hard-reject dua tren market context ngay trong slice dau.
- Multi-tenant/user account system.
- Frontend framework rewrite.

---

## 4. Release Plan

```text
V1.3.0  Optimization foundation and service boundaries
V1.3.1  Market context advisory integration
V1.3.2  Calibration proposal engine
V1.3.3  Config dry-run/apply/rollback workflow
V1.3.4  Replay impact comparison CLI/API
V1.3.5  Dashboard + docs + pre-prod signoff
```

Recommended execution order:

1. Phase A - Optimization foundation.
2. Phase B - Market context advisory integration.
3. Phase C - Calibration proposal engine.
4. Phase D - Config review/apply workflow.
5. Phase E - Replay impact tooling.
6. Phase F - Dashboard, QA, docs, release hardening.

---

# Phase A - Optimization Foundation

## A1. FilterEngine Boundary Refactor

### Goal

Giam rui ro khi them market context va calibration-driven rules bang cach tach rule implementation khoi `FilterEngine` lon hien tai.

### Scope

Keep stable:

- `FilterEngine(config, signal_repo, market_event_repo)`
- `FilterEngine.run(signal) -> FilterExecutionResult`
- `FilterExecutionResult` va `FilterResult`
- Boolean gate routing semantics

Extract internally:

```text
app/services/filter_rules/validation.py
app/services/filter_rules/trade_math.py
app/services/filter_rules/business.py
app/services/filter_rules/advisory.py
app/services/filter_rules/market_context.py
app/services/filter_rules/routing.py
```

### Acceptance Criteria

- Existing `tests/unit/test_filter_engine.py` pass without public API rewrite.
- No behavior change in baseline replay fixtures.
- `filter_engine.run()` still never raises for normal malformed signal inputs covered by tests.
- New modules are small enough to test independently.

## A2. Signal Bot Config Validation

### Goal

Khong cho admin dry-run/apply config sai kieu hoac unknown path nguy hiem.

### Behavior

- Add validation service or Pydantic model for `signal_bot_config`.
- Validate known sections: `allowed_symbols`, `allowed_timeframes`, `confidence_thresholds`, `cooldown_minutes`, RR config, strategy thresholds, rescoring, market context.
- Reject invalid scalar types, invalid threshold ranges, empty timeframe maps, and unsupported market context mode.
- Preserve backward compatibility for existing DB config by deep-merging defaults before validation.

### Acceptance Criteria

- Existing config from migrations validates.
- Invalid threshold type/range returns explicit validation error.
- Unknown top-level key is rejected unless intentionally whitelisted.
- Config cache reset behavior remains unchanged after apply.

## A3. Calibration Service Boundary

### Goal

Giup `analytics_controller.py` khong phinh to khi them proposal endpoint.

### Scope

Move calibration-specific aggregation/proposal building into service/repository helpers:

```text
app/services/calibration_report.py
app/services/calibration_proposals.py
```

Controller responsibilities:

- auth;
- query param validation;
- call service;
- return response.

### Acceptance Criteria

- Existing `/api/v1/analytics/calibration/report` response remains compatible.
- Proposal service can be unit-tested without FastAPI client.
- SQL query shape remains explicit and SQLAlchemy 2.0 style.

## A4. Replay Service Boundary

### Goal

Cho CLI, proposal review, va future API dung chung replay logic.

### Scope

Add service:

```text
app/services/replay_service.py
```

Responsibilities:

- load payload dicts;
- validate/normalize payload;
- run filter engine with supplied config;
- optionally compare two configs;
- return deterministic record and summary objects.

`scripts/replay_payloads.py` becomes a thin CLI wrapper.

### Acceptance Criteria

- Existing replay CLI tests still pass.
- Replay service has unit tests for ok/error/compare paths.
- CLI output remains JSONL-compatible.

---

# Phase B - Market Context Advisory Integration

## B1. Config Flags

### Goal

Cho phep bat/tat market context checks bang DB config, mac dinh an toan.

### Config

Add to `signal_bot_config`:

```json
{
  "market_context": {
    "enabled": false,
    "regime_mismatch_mode": "WARN",
    "snapshot_max_age_minutes": 10
  }
}
```

### Acceptance Criteria

- Default config merge khong doi behavior hien tai.
- Khi `enabled=false`, filter result khong thay doi.
- Config doc co mo ta ro `WARN` la advisory-only.

## B2. Snapshot Lookup Tolerance

### Goal

`MarketContextRepository.find_snapshot()` khong nen yeu cau `bar_time` match tuyet doi.

### Behavior

- Tim snapshot cung `symbol`, `timeframe`, `source` optional.
- Uu tien snapshot gan `bar_time` nhat trong `snapshot_max_age_minutes`.
- Neu khong co snapshot hop le, skip rule va khong reject.

### Acceptance Criteria

- Unit/integration tests cover exact match, nearest match, stale snapshot, missing snapshot.
- Add/verify index for nearest snapshot lookup, recommended:

```sql
CREATE INDEX IF NOT EXISTS idx_market_context_symbol_tf_source_bar_time
ON market_context_snapshots(symbol, timeframe, source, bar_time DESC);
```

## B3. Filter Pipeline Integration

Cam `MarketContextService.compare_regime()` vao `FilterEngine` sau hard business rules, truoc advisory warnings.

### Behavior

- Neu backend regime match payload regime: persist `BACKEND_REGIME_MISMATCH` PASS.
- Neu mismatch: persist WARN MEDIUM, route `PASS_WARNING` theo boolean gate.
- Neu thieu snapshot: skip hoac INFO `BACKEND_CONTEXT_MISSING` tuy implementation plan chot.
- Khong tao FAIL trong V1.3.1.

### Acceptance Criteria

- Webhook valid co snapshot mismatch -> `PASS_WARNING`, route `WARN`.
- Webhook valid khong co snapshot -> behavior hien tai khong doi.
- `filter_engine.run()` van khong raise exception.

---

# Phase C - Calibration Proposal Engine

## C1. Proposal Model

### Goal

Bien calibration insight thanh config proposal co the review.

### API

Add:

```text
GET /api/v1/analytics/calibration/proposals?days=90&min_samples=30
```

Response shape:

```json
{
  "period_days": 90,
  "min_samples": 30,
  "generated_at": "2026-05-02T00:00:00Z",
  "current_config_version": 4,
  "proposals": [
    {
      "id": "confidence_thresholds.5m.raise.20260502",
      "config_path": "confidence_thresholds.5m",
      "current": 0.78,
      "suggested": 0.81,
      "direction": "TIGHTEN",
      "reason": "5m low-confidence closed outcomes have negative avg R",
      "sample_health": {
        "samples": 42,
        "win_rate": 0.38,
        "avg_r": -0.12
      },
      "confidence": "MEDIUM",
      "risk": "May reduce signal count on 5m"
    }
  ]
}
```

### Acceptance Criteria

- No proposal khi sample < `min_samples`.
- Proposal include current value tu DB config.
- Recommendation khong mutate DB.
- Unit tests cover tighten, relax/watch/no-op, insufficient data.

## C2. Guardrail Rules

### Goal

Tranh overfit va config jump qua lon.

### Rules

- Confidence threshold suggestion max step: `0.03` per proposal.
- RR target/min suggestion max step: `10%` per proposal.
- Require at least 2 independent buckets before global rule recommendation.
- Any proposal with samples below `min_samples * 2` gets confidence `LOW`.

### Acceptance Criteria

- Guardrails enforced in service tests.
- Proposal response explains clamped suggestion when applicable.

---

# Phase D - Config Review, Apply, Rollback

## D1. Config Dry-Run Diff

### Goal

Admin co the xem patch se doi gi truoc khi apply.

### API

Add:

```text
POST /api/v1/admin/config/signal-bot/dry-run
```

Request:

```json
{
  "config_value": {
    "confidence_thresholds": {"5m": 0.81}
  },
  "change_reason": "Raise 5m threshold after 90d calibration review"
}
```

Response includes:

- current version;
- merged config preview;
- changed paths;
- validation errors/warnings.

### Acceptance Criteria

- Dry-run does not write `system_configs` or audit logs.
- Invalid config path/type returns 400 with clear error.

## D2. Apply Reviewed Proposal

### Goal

Apply config patch sau khi da review, co audit ro rang.

### Behavior

- Reuse existing `PUT /api/v1/admin/config/signal-bot` or add proposal-specific endpoint.
- Require `change_reason` >= 10 chars.
- Audit log stores old/new config and changed_by.
- Reset config cache after commit.

### Acceptance Criteria

- Config version increments exactly once.
- `signals.config_version` on later webhook records new version.
- Audit log visible through existing endpoint.

## D3. Rollback By Version

### Goal

Cho phep quay lai config version truoc do neu proposal lam ket qua xau.

### API

Add:

```text
POST /api/v1/admin/config/signal-bot/rollback
```

Request:

```json
{
  "target_version": 4,
  "change_reason": "Rollback after replay showed warning route spike"
}
```

### Acceptance Criteria

- Rollback tao version moi, khong sua audit history cu.
- Reject target version khong ton tai.
- Audit log ghi rollback reason.

---

# Phase E - Replay Impact Tooling

## E1. Config-Aware Replay CLI

### Goal

Nang `scripts/replay_payloads.py` de replay payload voi config thuc te hoac config override.

### CLI

```bash
python scripts/replay_payloads.py \
  --input docs/examples/v11_sample_payloads \
  --output /tmp/replay.jsonl \
  --config-file /tmp/proposed_config.json
```

Optional:

```bash
--compare-config-file /tmp/current_config.json
--database-url postgresql+psycopg://...
--config-db-key signal_bot_config
```

### Acceptance Criteria

- Existing dry-run behavior van pass.
- Replay co the load config JSON file.
- Compare mode outputs old/new decision, route, server_score, changed rule codes.

## E2. Replay Summary

### Goal

Cho admin thay impact tong quat truoc khi apply config.

### Output

JSONL per signal plus terminal summary:

```json
{
  "total": 120,
  "changed_decisions": 14,
  "main_to_warn": 7,
  "pass_to_reject": 0,
  "reject_to_pass": 1,
  "new_failed_rules": {"MIN_CONFIDENCE_BY_TF": 6},
  "new_warn_rules": {"BACKEND_REGIME_MISMATCH": 9}
}
```

### Acceptance Criteria

- Summary deterministic for same input/config.
- Tests cover compare mode and invalid payload handling.

---

# Phase F - Dashboard, QA, Docs

## F1. Dashboard Decision Intelligence Panel

### Goal

Dashboard hien thi dung workflow V1.3:

```text
Calibration proposal -> replay impact -> config version -> audit history
```

### UI Requirements

- Show proposal cards with current/suggested values.
- Show sample health and risk text.
- Show market-context mismatch rate.
- Show config version and latest config audit reason.
- No in-dashboard auto-apply without auth/admin endpoint.

### Acceptance Criteria

- Dashboard works on desktop and mobile.
- Auth still required.
- No token/secret exposed in rendered HTML except existing safe dashboard token injection behavior.

## F2. Docs Update

### Scope

- `docs/API_REFERENCE.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/FILTER_RULES.md`
- `docs/QA_STRATEGY.md`
- `docs/VERSION_HISTORY.md`
- `docs/LOCAL_SMOKE_CHECKLIST.md`

### Acceptance Criteria

- Docs describe V1.3 endpoints/config/rules.
- Stale V1.1 headings are corrected where touched.
- Release handoff doc created before merge.

## F3. Verification Matrix

### Required commands

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest -q
bash scripts/smoke_local.sh
python scripts/db/migrate.py apply
python scripts/db/migrate.py status
```

### Required manual QA

- Valid webhook happy path.
- Duplicate/idempotency path.
- Invalid JSON/schema/auth path.
- Market context missing/match/mismatch paths.
- Outcome open/close flow.
- Calibration proposal endpoint.
- Config dry-run/apply/rollback.
- Replay compare CLI.
- Dashboard visual QA.

---

## 5. Suggested PR Slicing

1. **PR-1:** V1.3 docs baseline + FilterEngine boundary refactor.
2. **PR-2:** Signal bot config validation service.
3. **PR-3:** Calibration service boundary + existing report compatibility.
4. **PR-4:** Replay service boundary + CLI compatibility.
5. **PR-5:** Market context config flags, repository tolerance, index migration.
6. **PR-6:** FilterEngine market context advisory integration.
7. **PR-7:** Calibration proposal service + API.
8. **PR-8:** Config dry-run/apply validation + rollback.
9. **PR-9:** Replay CLI config/compare mode.
10. **PR-10:** Dashboard Decision Intelligence panel.
11. **PR-11:** Docs, smoke, release handoff, final V1.3 signoff.

---

## 6. Definition Of Done

V1.3 done khi:

- `FilterEngine` rule implementation da tach module nhung public API va routing semantics khong doi.
- `signal_bot_config` co validation truoc dry-run/apply va migration default config validate thanh cong.
- Calibration/report/proposal logic nam trong service testable, controller khong phinh them business logic.
- Replay logic co service dung chung, CLI chi la wrapper mong.
- Market context mismatch co the route signal sang `PASS_WARNING` khi config enabled.
- Calibration proposals co current/suggested/diff/sample health va khong mutate DB.
- Config dry-run/apply/rollback co audit va versioning ro rang.
- Replay compare cho thay impact cua config change truoc khi apply.
- Dashboard the hien du workflow decision intelligence.
- Full unit/integration suite pass voi PostgreSQL test DB.
- Smoke local pass.
- Docs/API/schema/version history da update.
