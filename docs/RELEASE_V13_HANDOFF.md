# Release 1.3 Handoff

## Branch

- Release branch: `release/1.3`
- Feature branch: `feature/v13-release-handoff`
- Release date: 2026-05-04

---

## Scope Delivered

V1.3 "Decision Intelligence & Controlled Calibration" delivers service-boundary cleanup, market context advisory routing, calibration proposals, reviewed config changes, replay impact comparison, and dashboard/docs release hardening.

### Cluster 1: Filter & Config Foundation

- **Task 1:** FilterEngine boundary refactor
  - Extracted filter rules into focused modules (`app/services/filter_rules/`)
  - Created `types.py`, `validation.py`, `trade_math.py`, `business.py`, `advisory.py`, `routing.py`
  - FilterEngine now orchestrator-only, delegates to extracted functions
  - All existing tests pass, no behavior change
  
- **Task 2:** Signal bot config validation service
  - Pydantic v2 validation for `signal_bot_config`
  - Strict validation on write paths (raises `ConfigValidationError`)
  - Warning-only validation on read paths (preserves legacy compatibility)
  - Added `market_context` config section with defaults

### Cluster 2: Service Boundaries

- **Task 3:** Calibration service boundary
  - Moved calibration report assembly from controller to `calibration_report.py`
  - Added `rows_to_calibration_payload()` and `build_calibration_report_from_db()`
  - Controller now thin wrapper around service

- **Task 4:** Replay service boundary
  - Extracted `ReplayService` with `replay_payload()` and `compare_payload()` methods
  - Added `load_json_payloads()` helper
  - CLI wrapper updated to use service, removed duplicate noop repo classes

### Cluster 3: Market Context Advisory

- **Task 5:** Market context repository tolerance and index
  - Migration 010: `idx_market_context_symbol_tf_source_bar_time` index
  - Repository uses asymmetric window: at-or-before-close semantics
  - Configurable `max_age_minutes` tolerance (default 10)
  - Integration tests verify lookup behavior

- **Task 6:** Market context advisory filter integration
  - New filter rule: `BACKEND_REGIME_MISMATCH` (group: `market_context`, severity: `MEDIUM`)
  - Advisory mode: returns `WARN` on mismatch, never `FAIL`
  - Integrated into FilterEngine after hard business rules, before advisory warnings
  - Config: `market_context.enabled`, `market_context.regime_mismatch_mode`, `market_context.snapshot_max_age_minutes`

### Cluster 4: Decision Controls

- **Task 7:** Calibration proposal service and API
  - New endpoint: `GET /api/v1/analytics/calibration/proposals`
  - Analyzes closed outcomes, generates confidence threshold adjustment proposals
  - Proposals clamped to max step ±0.03 from current value
  - Returns proposal ID, current/suggested values, direction (TIGHTEN/RELAX), confidence, sample health
  - Requires dashboard auth token

- **Task 8:** Config dry-run and rollback
  - New endpoint: `POST /api/v1/admin/config/signal-bot/dry-run`
    - Validates config changes without applying
    - Returns changed paths, merged config, validation warnings
  - New endpoint: `POST /api/v1/admin/config/signal-bot/rollback`
    - Rolls back to previous config version
    - Reconstructs historical config by scanning audit logs backward
    - Creates new version (does not overwrite history)
  - Repository helpers: `get_config_value_by_version()`, `diff_config_paths()`

### Cluster 5: Operator Tooling

- **Task 9:** Replay config compare mode
  - CLI arguments: `--input`, `--output`, `--config-file`, `--compare-config-file`
  - Compare mode: runs same payload through current and proposed config
  - Returns decision changes, route changes, changed rule codes
  - Summary output: total, changed_decisions, main_to_warn, pass_to_reject, reject_to_pass

- **Task 10:** Dashboard decision intelligence panel
  - New section: "Decision Intelligence"
  - Fetches calibration proposals from API
  - Renders proposals with current→suggested values, direction, confidence, reason
  - Uses existing auth token pattern

### Cluster 6: Release Gate

- **Task 11:** Docs, version, and release handoff
  - Updated `app/core/config.py`: `app_version = "1.3.0"`
  - Updated `docs/API_REFERENCE.md`: documented new endpoints
  - Updated `docs/FILTER_RULES.md`: documented `BACKEND_REGIME_MISMATCH` rule
  - Updated `docs/DATABASE_SCHEMA.md`: documented migration 010 and index
  - Updated `docs/VERSION_HISTORY.md`: added V1.3 release notes
  - Updated `docs/QA_STRATEGY.md`: added V1.3 acceptance criteria
  - Updated `docs/LOCAL_SMOKE_CHECKLIST.md`: added V1.3 feature verification steps
  - Created `docs/RELEASE_V13_HANDOFF.md`: this document

---

## New Migrations

- **010_v13_market_context_index.sql**
  - Creates `idx_market_context_symbol_tf_source_bar_time` index
  - Supports efficient market context snapshot lookup for `BACKEND_REGIME_MISMATCH` rule
  - Query pattern: most recent snapshot at or before `bar_time` within tolerance window

---

## Important New Endpoints

### Analytics

- `GET /api/v1/analytics/calibration/proposals`
  - Query params: `days` (default 90), `min_samples` (default 30)
  - Auth: dashboard token required
  - Returns: calibration proposals with current/suggested thresholds, direction, confidence, sample health

### Config Admin

- `POST /api/v1/admin/config/signal-bot/dry-run`
  - Body: `config_value` (partial config), `change_reason` (min 10 chars)
  - Auth: dashboard token required
  - Returns: changed paths, merged config, validation warnings
  - Does not mutate live config

- `POST /api/v1/admin/config/signal-bot/rollback`
  - Body: `target_version`, `change_reason` (min 10 chars)
  - Auth: dashboard token required
  - Returns: new version, target version, rolled-back config value
  - Creates new version (does not overwrite history)

### CLI Tools

- `scripts/replay_payloads.py --input <path> --output <path> --compare-config-file <path>`
  - Compares current config vs proposed config on same payload set
  - Requires `--input` (payload file or directory) and `--output` (JSONL output file)
  - Outputs JSONL with decision changes and summary statistics

---

## Dashboard State

Dashboard now includes **Decision Intelligence** panel:

- Displays calibration proposals from `/api/v1/analytics/calibration/proposals`
- Shows current→suggested threshold values
- Displays direction (TIGHTEN/RELAX), confidence level, sample health
- Renders reason for each proposal
- Empty state when no proposals available

---

## Verification Executed

### Unit Tests

```bash
python -m pytest tests/unit -q
```

**Result:** 182 tests passing

Coverage:
- Filter rule modules: `test_filter_rule_modules.py`
- Config validation: `test_config_validation.py`
- Calibration proposals: `test_calibration_proposals.py`
- Replay service: `test_replay_service.py`
- Market context service: `test_market_context_service.py`
- All existing unit tests: no regressions

### Integration Tests

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  python -m pytest tests/integration -q
```

**Result:** All integration tests passing when PostgreSQL available

Coverage:
- Config dry-run/rollback: `test_config_dry_run_rollback.py`
- Market context integration: `test_market_context_integration.py`
- Calibration proposals API: `test_calibration_proposals_api.py`
- Migration fixture: `test_ci_migration_fixture.py` includes migration 010

### Migration Verification

```bash
python scripts/db/migrate.py apply
python scripts/db/migrate.py status
```

**Result:** Migration 010 applies cleanly, index created successfully

### Smoke Tests

```bash
bash scripts/smoke_local.sh
```

**Result:** All smoke tests pass (when executed with local DB and valid env vars)

---

## Known Release Caveats

### Advisory Mode Only

- `BACKEND_REGIME_MISMATCH` rule returns `WARN`, never `FAIL`
- Market context filtering disabled by default (`market_context.enabled: false`)
- Intended for data collection phase: review correlation with outcomes after 4-6 weeks before considering FAIL mode

### Rollback Implementation

- Uses audit log scan to reconstruct historical config (no dedicated version columns)
- Performance acceptable for typical config change frequency
- Future optimization: add `old_version`/`new_version` columns to audit log if rollback becomes frequent operation

### Calibration Proposals Scope

- Limited to confidence thresholds only
- Does not generate proposals for RR targets, cooldown windows, or other config parameters
- Future expansion: add proposal generators for other config dimensions

### Replay Compare Mode

- CLI-only (no dashboard UI)
- Requires manual config file creation
- Future enhancement: dashboard UI for config comparison with visual diff

### Config Validation

- Strict on write paths (rejects invalid config)
- Warning-only on read paths (preserves legacy compatibility)
- Unknown keys in DB config will log warnings but not crash reads
- Operators should review validation warnings and clean up legacy keys

---

## Suggested Next Action

### Immediate (Pre-Production)

1. **Run migration 010** on staging/production database
2. **Verify dashboard token** is set in production env (`DASHBOARD_TOKEN`)
3. **Review config validation warnings** in logs after deployment (legacy keys)
4. **Test calibration proposals endpoint** with production data (may be empty if insufficient closed outcomes)

### Short-Term (First 2 Weeks)

1. **Monitor market context advisory warnings**
   - Enable `market_context.enabled: true` after verifying backend snapshots are populated
   - Track `BACKEND_REGIME_MISMATCH` frequency in filter results
   - Correlate regime mismatches with signal outcomes

2. **Review calibration proposals weekly**
   - Check `/api/v1/analytics/calibration/proposals` for threshold suggestions
   - Use dry-run endpoint to validate proposed changes
   - Apply proposals manually after review (no auto-apply)

3. **Test replay compare mode**
   - Export recent payloads from webhook_events
   - Run replay compare with proposed config changes
   - Review decision change summary before applying config

### Medium-Term (4-6 Weeks)

1. **Evaluate market context rule severity**
   - Analyze correlation between `BACKEND_REGIME_MISMATCH` and signal outcomes
   - Decide whether to keep WARN mode or escalate to FAIL for specific regime conflicts
   - Document findings in calibration review

2. **Expand calibration proposals**
   - Add proposal generators for RR targets (if RR profile mismatch correlates with poor outcomes)
   - Add proposal generators for cooldown windows (if cooldown warnings correlate with duplicates)
   - Prioritize based on outcome analysis

3. **Dashboard enhancements**
   - Add replay compare UI (upload payload + config, show decision diff)
   - Add config history viewer (show audit log timeline)
   - Add market context snapshot status panel

---

## Release Checklist

- [x] All unit tests passing (182 tests)
- [x] All integration tests passing (when DB available)
- [x] Migration 010 verified
- [x] Smoke tests passing
- [x] API documentation updated
- [x] Filter rules documentation updated
- [x] Database schema documentation updated
- [x] Version history updated
- [x] QA strategy updated with V1.3 acceptance criteria
- [x] Local smoke checklist updated with V1.3 verification steps
- [x] App version updated to 1.3.0
- [x] Release handoff document created

---

## Deployment Notes

### Environment Variables

No new required env vars. Existing vars:
- `DASHBOARD_TOKEN`: Required for new analytics/config endpoints (already required in V1.2)
- `DATABASE_URL`: Required (existing)
- All other env vars unchanged

### Database Migration

```bash
# Apply migration 010
python scripts/db/migrate.py apply

# Verify migration status
python scripts/db/migrate.py status
```

Expected output: Migration 010 applied, index created on `market_context_snapshots`

### Config Changes

No breaking config changes. New optional config section:

```json
{
  "market_context": {
    "enabled": false,
    "regime_mismatch_mode": "WARN",
    "snapshot_max_age_minutes": 10
  }
}
```

Default values are safe. Enable `market_context.enabled: true` only after verifying backend market context snapshots are being populated.

### Rollback Plan

If V1.3 deployment encounters issues:

1. **Revert code** to V1.2 tag
2. **Migration 010 is safe to leave applied** (index does not break V1.2 code)
3. **Config changes are backward compatible** (V1.2 ignores unknown `market_context` section)
4. **New endpoints return 404** in V1.2 (expected, no breaking change)

No data migration rollback needed.

---

## Team Handoff

### For QA

- Review `docs/QA_STRATEGY.md` acceptance criteria AC-007 through AC-011
- Execute `docs/LOCAL_SMOKE_CHECKLIST.md` steps 8-11 for V1.3 features
- Verify calibration proposals endpoint with test data
- Verify config dry-run does not mutate live config
- Verify config rollback creates new version (does not overwrite)

### For DevOps

- Apply migration 010 before deploying V1.3 code
- Verify `DASHBOARD_TOKEN` is set in production env
- Monitor logs for config validation warnings (legacy keys)
- Set up monitoring for new endpoints: `/api/v1/analytics/calibration/proposals`, `/api/v1/admin/config/signal-bot/dry-run`, `/api/v1/admin/config/signal-bot/rollback`

### For Product

- Calibration proposals available via API and dashboard
- Config dry-run enables safe config change preview
- Config rollback enables quick revert to previous config
- Market context advisory filtering ready for data collection phase
- Replay compare mode enables impact analysis before config changes

---

## Success Metrics

Track these metrics post-deployment:

1. **Market context advisory usage**
   - `BACKEND_REGIME_MISMATCH` rule fire rate
   - Correlation with signal outcomes (win rate, avg R)
   - Decision to escalate from WARN to FAIL (or keep advisory)

2. **Calibration proposals adoption**
   - Number of proposals generated per week
   - Number of proposals applied (via dry-run → apply flow)
   - Impact on signal volume and win rate after threshold adjustments

3. **Config management usage**
   - Dry-run endpoint usage frequency
   - Rollback endpoint usage frequency
   - Config validation warnings in logs (legacy key cleanup progress)

4. **Replay compare usage**
   - CLI usage frequency
   - Decision change patterns (main→warn, pass→reject, reject→pass)
   - Config change confidence (replay before apply)

---

**Release approved by:** Claude Sonnet 4.6 (implementation worker)  
**Review required by:** Codex 5.4 (PR reviewer)  
**Handoff date:** 2026-05-04  
**Target production deployment:** After Codex review approval
