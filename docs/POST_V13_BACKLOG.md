# POST V1.3 BACKLOG - After Deploy Follow-Ups

Muc tieu cua backlog nay la gom cac viec khong blocking PR/release V1.3, nhung nen xu ly sau khi deploy `v1.3.0`, chay migration 010, smoke checklist, va monitor ban dau.

## Nguyen Tac

- Khong auto-trade.
- Khong tu dong apply calibration vao live config.
- Market context tiep tuc advisory-first cho den khi co du outcome data.
- Moi config change phai qua dry-run/replay/review/apply co audit.
- Khong sua routing theo `server_score`; boolean gate van la source of truth.

## Release Gate Can Xong Truoc Backlog

- Deploy `release/1.3` / tag `v1.3.0` len moi truong dich.
- Chay migration `migrations/010_v13_market_context_index.sql`.
- Verify health/version tra ve `1.3.0`.
- Chay smoke checklist V1.3 trong `docs/LOCAL_SMOKE_CHECKLIST.md`.
- Neu co PostgreSQL test DB, chay full integration suite voi `INTEGRATION_DATABASE_URL`.
- Giu `market_context.enabled=false` luc dau neu muon rollout an toan.

## P0 - Post-Deploy Verification

### V13-P0-001 - Chay Integration Suite Voi PostgreSQL That

**Ly do:** Local review hien tai co `130 skipped` do chua set `INTEGRATION_DATABASE_URL`.

**Scope:**
- Tao/chi dinh PostgreSQL test DB rieng.
- Chay:

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot_test' \
PYTHONPATH=. .venv/bin/pytest -q
```

**Acceptance:**
- Unit + integration pass, khong co skip do thieu DB.
- Neu fail do env/fixture, ghi ro vao release notes va fix rieng.

### V13-P0-002 - Smoke Migration Va Endpoint Tren Staging/Production

**Scope:**
- Verify migration 010 da apply va index ton tai.
- Verify endpoints:
  - `GET /api/v1/health` / version `1.3.0`
  - `GET /api/v1/analytics/calibration/proposals`
  - `POST /api/v1/admin/config/signal-bot/dry-run`
  - `POST /api/v1/admin/config/signal-bot/rollback` tren test config/version neu an toan

**Acceptance:**
- Smoke checklist pass.
- Khong co config validation warning bat thuong trong logs.

## P1 - Operator Tooling Improvements

### V13-P1-001 - Replay Summary Rule Breakdown

**Ly do:** Roadmap V1.3 co de xuat summary chi tiet hon hien tai.

**Scope:**
- Mo rong `app/services/replay_service.py` va `scripts/replay_payloads.py` summary de them:
  - `new_failed_rules`
  - `new_warn_rules`
  - optional `resolved_failed_rules`
  - optional `resolved_warn_rules`
- Dem theo `rule_code` khi compare current/proposed config.

**Acceptance:**
- Compare summary deterministic cho cung input/config.
- Unit tests cover rule breakdown.
- JSONL per-signal backward compatible.

### V13-P1-002 - DB-Backed Replay Config Loading

**Ly do:** CLI hien co `--config-db-key` nhung chu yeu la metadata; replay compare dang dua vao config file.

**Scope:**
- Them optional `--database-url` de load config tu `system_configs`.
- `--config-db-key` dung that su khi `--database-url` duoc set.
- Van giu `--config-file` / `--compare-config-file` cho workflow offline.

**Acceptance:**
- CLI load config tu DB test duoc.
- Khong doc nham production DB neu khong truyen explicit `--database-url`.
- Docs/API or smoke docs cap nhat cach dung.

### V13-P1-003 - Typed Schemas Cho Config/Proposal APIs

**Ly do:** Plan V1.3 co nhac `app/domain/schemas.py`, nhung PR V1.3 hien dung raw dict cho mot so endpoint admin/proposal.

**Scope:**
- Them Pydantic request/response models cho:
  - calibration proposals response
  - config dry-run request/response
  - config rollback request/response
- Giu response shape backward compatible.

**Acceptance:**
- FastAPI OpenAPI hien schema ro.
- Existing tests pass.
- Invalid payload errors van ro rang va khong leak secret.

## P1 - Dashboard Decision Intelligence

### V13-P1-004 - Dashboard Replay Impact Panel

**Ly do:** Roadmap muon dashboard hien workflow: proposal -> replay impact -> config version -> audit.

**Scope:**
- Hien thi replay compare summary gan day hoac huong dan operator upload/chay replay.
- It nhat dashboard can co placeholder state ro rang neu replay data chua co.
- Khong auto-apply tu dashboard.

**Acceptance:**
- Dashboard hien proposal va replay impact/status trong cung Decision Intelligence area.
- Mobile/desktop van doc duoc.
- Auth khong thay doi.

### V13-P1-005 - Dashboard Config Version Va Latest Audit Reason

**Scope:**
- Hien current `signal_bot_config` version.
- Hien latest audit log reason/changed_at.
- Link/operator hint den dry-run/apply/rollback workflow.

**Acceptance:**
- Operator nhin duoc dang o config version nao truoc khi review proposal.
- Khong expose token/secret trong HTML.

### V13-P1-006 - Market Context Health Metrics Tren Dashboard

**Scope:**
- Hien:
  - `BACKEND_REGIME_MISMATCH` count/rate
  - missing snapshot rate neu co du data de tinh
  - PASS/WARN distribution khi `market_context.enabled=true`
- Co filter period tuong tu analytics dashboard hien co.

**Acceptance:**
- Operator biet co nen bat/tat market context advisory hay khong.
- Query duoc index-friendly, khong lam cham dashboard.

## P2 - Calibration Expansion

### V13-P2-001 - Bo Sung Test Cho RELAX Proposal Path

**Ly do:** Unit tests hien cover tighten clamp/insufficient/unknown timeframe, chua cover relax ro rang.

**Scope:**
- Them test cho proposal khi suggested thap hon current.
- Verify max step `-0.03` va direction `RELAX`.

**Acceptance:**
- Tests fail neu direction/clamp sai.

### V13-P2-002 - Proposal Cho RR Targets / RR Minimums

**Scope:**
- Sau khi co du outcome data, tao proposal generator cho:
  - `rr_target_by_type.*`
  - `rr_min_base`
  - `rr_min_squeeze`
- Guardrail max step 10% moi proposal.

**Acceptance:**
- Khong tao proposal neu sample < `min_samples`.
- Proposal co risk text va sample health.
- Khong mutate DB.

### V13-P2-003 - Proposal Cho Cooldown Windows

**Scope:**
- Phan tich correlation giua `COOLDOWN_ACTIVE`, duplicate suppression, va outcomes.
- De xuat tang/giam `cooldown_minutes.<tf>` neu co du mau.

**Acceptance:**
- Co guardrail max step hop ly theo timeframe.
- Co replay compare truoc khi apply.

### V13-P2-004 - Global Rule Recommendation Guardrail

**Scope:**
- Yeu cau it nhat 2 independent buckets truoc khi de xuat global rule/config change.
- Hien ro confidence `LOW/MEDIUM/HIGH` dua tren sample health.

**Acceptance:**
- Khong overfit tu mot bucket don le.
- Tests cover insufficient independent buckets.

## P2 - Market Context Follow-Up

### V13-P2-005 - Market Context Advisory Review Sau 2-4 Tuan

**Scope:**
- Bat `market_context.enabled=true` khi backend snapshots on dinh.
- Theo doi:
  - tan suat `BACKEND_REGIME_MISMATCH`
  - PASS_WARNING rate
  - outcome correlation cua mismatch vs match

**Acceptance:**
- Co bao cao ngan ve viec giu WARN, tat rule, hay can research FAIL mode.
- Khong doi sang FAIL neu chua co evidence.

### V13-P2-006 - Evaluate Index/Query Performance

**Scope:**
- Chay `EXPLAIN ANALYZE` cho market context lookup tren data that.
- Xem co can index phu `(symbol, timeframe, bar_time DESC)` khi query khong filter source khong.

**Acceptance:**
- Query dashboard/webhook khong bi slow.
- Neu them index moi thi tao migration rieng.

## P3 - Release Process Hygiene

### V13-P3-001 - Escalation Review Neu Can Strict Plan Compliance

**Ly do:** Plan V1.3 yeu cau escalation review cho Cluster 3/4/6 neu reviewer kha dung.

**Scope:**
- Nho mot high-capability reviewer doc PR/release diff sau merge hoac truoc production cutover.
- Tap trung architecture, query semantics, rollback correctness, release risk.

**Acceptance:**
- Khong co blocking findings truoc production rollout.
- Findings non-blocking duoc dua vao backlog nay.

### V13-P3-002 - Cleanup Git Sau Release

**Scope:**
- Merge/sync `release/1.3` ve `main` neu chua lam.
- Tao/verify tag `v1.3.0`.
- Don feature branches da merge.

**Acceptance:**
- `main`, `release/1.3`, tag `v1.3.0` ro rang.
- Khong mat commit release.

## Suggested Execution Order Sau Deploy

1. `V13-P0-001` va `V13-P0-002` de dong release confidence.
2. `V13-P1-001` replay summary rule breakdown.
3. `V13-P1-005` config version/latest audit tren dashboard.
4. `V13-P1-006` market context health metrics.
5. `V13-P1-004` replay impact panel.
6. `V13-P1-003` typed schemas.
7. P2 calibration/market-context expansion sau khi co 2-4 tuan outcome data.
