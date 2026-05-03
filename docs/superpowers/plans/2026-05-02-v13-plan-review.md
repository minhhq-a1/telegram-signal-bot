# V1.3 Implementation Plan Review

**Reviewed:** 2026-05-02
**Plan file:** `docs/superpowers/plans/2026-05-02-v13-decision-intelligence.md`
**Roadmap file:** `docs/ROADMAP_V1.3.md`
**Overall score:** 85/100 - Solid plan, needs 4 fixes before execution.

---

## Strengths

1. **Spec-to-task mapping is complete.** Roadmap Phase A-F maps 1:1 to Tasks 0-11 with no scope gaps.

2. **Invariants preserved.** No task changes `FilterEngine.run()` public API, boolean gate routing, persist-before-notify, or idempotency semantics.

3. **TDD approach is consistent.** Every task writes tests first, verifies import failure, implements, verifies pass.

4. **FilterEngine refactor is safe.** Current file is 391 lines. Plan splits into 6 rule modules but preserves exact `run()` orchestration order. Existing `test_filter_engine.py` (20.9KB, largest test file in project) serves as characterization test suite.

5. **Calibration service boundary is justified.** `analytics_controller.py` is 972 lines. The `/calibration/report` endpoint (lines 560-612) has ~50 lines of inline SQL assembly that belongs in a service.

6. **Replay service extraction is clean.** CLI wrapper (`scripts/replay_payloads.py`, 91 lines) already has `_NoopSignalRepo`/`_NoopMarketRepo` that move naturally into service.

---

## Issues To Fix Before Execution

### Issue 1 (HIGH): Config validation may reject production data

**Location:** Task 2, Step 5

**Problem:** Plan adds `validate_signal_bot_config()` call in `get_signal_bot_config()` (read path) with `SignalBotConfigModel(extra="forbid")`. If the DB config was manually patched with an unknown key (e.g., `"experimental_flag": true`), validation will raise `ConfigValidationError` on every webhook — breaking production.

**Current state:** `config_repo.py` `_deep_merge` accepts any key silently. No validation exists today.

**Fix:** Validate only on **write** paths (`update_config_with_audit`, dry-run endpoint). On read paths (`get_signal_bot_config`, `get_signal_bot_config_with_version`), either skip validation or catch `ConfigValidationError` and log a warning without raising. This preserves backward compatibility while protecting new writes.

**Affected plan steps:** Task 2 Step 5.

---

### Issue 2 (HIGH): Non-sargable ORDER BY in market context lookup

**Location:** Task 5, Step 2

**Problem:** Plan uses `ORDER BY ABS(EXTRACT(epoch FROM bar_time - :target))` to find the nearest snapshot. This expression is non-sargable: PostgreSQL cannot use the `bar_time DESC` index for this sort. On a large `market_context_snapshots` table, this becomes a sequential scan over all rows matching `(symbol, timeframe, source)`.

**Current state:** `market_context_repo.py` uses exact `bar_time` match (`WHERE bar_time == bar_time`). The plan's index `(symbol, timeframe, source, bar_time DESC)` is designed for range scans, not expression sorts.

**Fix:** Replace with a two-phase approach that uses the index:

```python
# Find nearest snapshot within tolerance window using index scan
stmt = (
    select(MarketContextSnapshot)
    .where(MarketContextSnapshot.symbol == symbol)
    .where(MarketContextSnapshot.timeframe == timeframe)
    .where(MarketContextSnapshot.bar_time >= lower)
    .where(MarketContextSnapshot.bar_time <= upper)
    .order_by(MarketContextSnapshot.bar_time.desc())
    .limit(1)
)
```

This prefers the most recent snapshot within the window (usually the right semantic for trading signals) and uses the DESC index efficiently. If absolute-nearest is truly needed, fetch the two nearest (one before, one after) and compare in Python.

**Affected plan steps:** Task 5 Step 2.

---

### Issue 3 (MEDIUM): Circular import risk after FilterEngine refactor

**Location:** Task 1 Step 7 + Task 6 Step 2

**Problem:** Current import chain:

```
market_context_service.py -> filter_engine.py (imports FilterResult)
```

After Task 1, `FilterResult` moves to `filter_rules/types.py`. Plan keeps re-export in `filter_engine.py`, so existing import works. But Task 6 creates:

```
filter_rules/market_context.py -> market_context_service.py -> filter_engine.py -> filter_rules/__init__.py -> filter_rules/types.py
```

This is technically not circular (no cycle), but it creates a fragile chain where `filter_rules/market_context.py` depends on `filter_engine.py` indirectly through `market_context_service.py`. If anyone adds an import of `filter_rules` into `filter_engine.py`'s module-level scope (which Task 1 already does), the chain becomes:

```
filter_rules/market_context.py -> market_context_service.py -> filter_engine.py -> filter_rules/market_context.py  [CYCLE]
```

**Fix:** In Task 1, also update `market_context_service.py` line 3 from:

```python
from app.services.filter_engine import FilterResult
```

to:

```python
from app.services.filter_rules.types import FilterResult
```

This breaks the chain cleanly. Cost: one extra line change in Task 1.

**Affected plan steps:** Task 1 Step 7 (add this change), Task 6 Step 2 (verify no cycle).

---

### Issue 4 (MEDIUM): Rollback migration not specified

**Location:** Task 8, Step 4

**Problem:** Plan says "add a new migration with `old_version` and `new_version`" but does not provide the SQL. `SystemConfigAuditLog` currently has columns: `id, config_key, old_value, new_value, changed_by, change_reason, created_at`. There is no `version` column, so rollback-by-version requires either:

- (a) A new migration adding `old_version INTEGER, new_version INTEGER` to `system_config_audit_log`, or
- (b) Computing version from `SystemConfig.version` at query time.

**Fix:** Option (b) is simpler and avoids a schema migration. `ConfigRepository.get_config_value_by_version()` can scan audit logs backward from current version. Since versions increment by 1, the Nth-from-latest audit log entry's `old_value` is version `current - N`. Alternatively, write a small migration:

```sql
-- Migration 011: Add version tracking to config audit log for rollback support.
ALTER TABLE system_config_audit_log
    ADD COLUMN IF NOT EXISTS old_version INTEGER,
    ADD COLUMN IF NOT EXISTS new_version INTEGER;
```

And populate `old_version/new_version` in `update_config_with_audit()`. Either approach works, but plan should specify which one.

**Affected plan steps:** Task 8 Step 4.

---

## Minor Observations

### Task 3: Duplicate SQL assembly

Plan Step 2 creates `build_calibration_report_from_db()` with SQL nearly identical to `analytics_controller.py` lines 568-607. Step 3 replaces the controller body with a service call. Plan should explicitly say "remove the inline SQL from the controller" to avoid leaving dead code.

### Task 4: Duplicate noop repos

Plan creates `_NoopSignalRepo` and `_NoopMarketRepo` in `replay_service.py` — exact copies of the same classes in `replay_payloads.py`. After refactor, CLI imports from service, so the CLI copies become dead code. Plan Step 4 should say "remove `_NoopSignalRepo` and `_NoopMarketRepo` from `scripts/replay_payloads.py`."

### Task 1: Verification scope too narrow

Plan Step 8 runs only `test_filter_engine.py`, `test_filter_rule_modules.py`, `test_strategy_validator.py`, `test_rescoring_engine.py`. But other files also import `FilterResult` from `filter_engine.py`:

- `market_context_service.py` (and its test `test_market_context_service.py`)
- `webhook_ingestion_service.py` (and integration tests)

Should run full `python -m pytest tests/unit -q` after Task 1 to catch any broken imports.

### Task 7: threshold_suggestions field contract

`calibration_report.py` `_build_threshold_suggestions()` produces `"current": None` (line 122). But `build_calibration_proposals()` in Task 7 accesses `current_config.get("confidence_thresholds", {}).get(timeframe)` — it reads current value from config, not from the report. This is correct but fragile: the `"current"` field in the report is never used by the proposal builder. Consider removing it from the report or documenting the contract clearly.

---

## Recommended Execution Sequence

No change to the plan's task ordering (0 -> 11). But add these checkpoints:

1. **After Task 1:** Run `python -m pytest tests/unit -q` (full unit suite, not just filter tests).
2. **After Task 2:** Verify existing DB config passes validation before deploying.
3. **After Task 5:** Verify index is used with `EXPLAIN ANALYZE` on a test query.
4. **After Task 8:** Verify rollback creates a new version (not overwrites).
5. **After Task 11:** Full verification matrix from roadmap section F3.

---

## Codex Assessment

Reviewed against current code on `release/1.3` / `main` baseline:

- `app/repositories/config_repo.py`
- `app/repositories/market_context_repo.py`
- `app/services/market_context_service.py`
- `app/domain/models.py`

### Overall

The review is technically strong and worth taking seriously. I agree with the 4 main issues. The highest-signal points are:

1. strict config validation on the read path would be dangerous in production;
2. the proposed nearest-snapshot SQL sort is expensive if implemented with an expression sort;
3. the current `market_context_service.py -> filter_engine.py` import dependency is a real fragility during refactor;
4. rollback-by-version needs an explicit persistence strategy, not a vague placeholder.

### Where I Agree Fully

#### Issue 1: config validation on read path

Agree. Current `ConfigRepository.get_signal_bot_config()` is on the hot path for webhook processing. With the current repository behavior, `_deep_merge()` accepts unknown keys silently. If V1.3 adds `SignalBotConfigModel(extra="forbid")` and raises on reads, one manual DB patch with an unknown key could break every webhook.  

Write-path validation is the safe default. Read-path validation should be warn-only or skipped.

#### Issue 3: import-chain fragility

Agree. Current `app/services/market_context_service.py` imports `FilterResult` from `app/services/filter_engine.py`. Once `FilterResult` moves into `filter_rules/types.py`, leaving the old import path in place creates an avoidable chain that becomes brittle as soon as `filter_rules/market_context.py` is introduced.

The direct import fix is low cost and should be part of the refactor plan.

#### Minor observations

Agree on all 4:

- Task 3 should explicitly remove the old inline calibration SQL from the controller.
- Task 4 should explicitly remove duplicate `_Noop*` classes from the CLI.
- Task 1 should run the full unit suite after the refactor, not only the targeted tests.
- Task 7 should document that calibration proposals read current threshold values from live config, not from report payload fields.

### Where I Agree With One Adjustment

#### Issue 2: nearest snapshot query

Agree on the performance concern, but I would separate **query shape** from **business semantics**.

The review is correct that this plan shape is a problem on PostgreSQL:

```python
ORDER BY ABS(EXTRACT(epoch FROM bar_time - :target))
```

That sort is non-sargable and does not align with the intended `(symbol, timeframe, source, bar_time DESC)` index.

The only nuance is semantic:

- `nearest snapshot within tolerance window`
- `most recent snapshot within tolerance window`

These are not always the same thing.

If product semantics are "use the latest backend context that was available around the bar," then ordering by `bar_time DESC` is the right answer and the review's proposed fix is correct.

If semantics are truly "pick the closest timestamp," the better implementation is:

1. use the index to fetch at most one candidate before `bar_time`;
2. use the index to fetch at most one candidate after `bar_time`;
3. compare the two timestamps in Python.

That preserves absolute-nearest semantics without paying for an expression sort across the window.

#### Issue 4: rollback strategy

Agree that the plan must choose one approach. I do not agree equally with both options.

The review says either of these can work:

- derive versions by scanning audit logs backward from current version;
- add explicit `old_version/new_version` columns.

I would prefer explicit version columns. The backward-scan approach couples rollback correctness to audit ordering assumptions and makes reasoning about partial historical gaps less robust. A small migration is cleaner and easier to audit later.

### Bottom Line

If I were updating the plan, I would take the review almost entirely as-is, with only these clarifications:

1. for market context lookup, explicitly choose between "most recent" and "absolute nearest" semantics before locking the query design;
2. for rollback, prefer schema-backed audit versioning over implicit reconstruction from log order.

---

## Claude Response To Codex Assessment

### Issue 2: Snapshot semantic — no need to deliberate further

Codex asks to "explicitly choose between most recent and absolute nearest." I believe this is already settled by the product context:

- `bar_time` is the candle close timestamp from TradingView.
- Snapshots are written by the backend data pipeline, which runs **before or at** `bar_time`, rarely after.
- The question being answered is: "what was the backend's regime view when this bar closed?"

**"Most recent snapshot within the tolerance window" is the correct semantic.** A snapshot from 2 minutes before `bar_time` is more relevant than one from 8 minutes after (if it even exists). `ORDER BY bar_time DESC LIMIT 1` within the `[lower, upper]` window is the right query — no 2-query approach needed.

The 2-candidate approach Codex describes (fetch one before + one after, compare in Python) adds complexity for a case that does not arise in practice. Snapshots arriving after `bar_time` would mean the pipeline ran late, and in that scenario the pre-bar snapshot is the one the signal decision should have been based on anyway.

**Decision: Use `ORDER BY bar_time DESC LIMIT 1` within tolerance window. No further semantic discussion needed.**

### Issue 4: Rollback — prefer audit log scan over migration

Codex prefers explicit `old_version/new_version` columns. I disagree for this project's current scale and constraints:

**Why audit log scan is sufficient:**

1. `update_config_with_audit()` creates the audit log entry **in the same transaction** as the version increment (`db.flush()`). There are no gaps unless someone modifies the DB directly with raw SQL — which would also break column-based versioning.

2. Versions increment by exactly +1 (line 207: `config.version = int(config.version or 1) + 1`). The Nth audit log entry from the top corresponds to version `current - N`. This is deterministic, not an "ordering assumption."

3. Adding columns means: new migration (011), model change in `models.py`, update `update_config_with_audit()` to populate both columns, handle NULL for existing audit rows (backfill or defensive code). That is 4 touch points for a feature that may see single-digit uses in production.

**Reference implementation:**

```python
def get_config_value_by_version(self, config_key: str, target_version: int) -> dict | None:
    current = self.db.execute(
        select(SystemConfig).where(SystemConfig.config_key == config_key)
    ).scalar_one_or_none()
    if not current:
        return None
    if current.version == target_version:
        return current.config_value
    logs = self.db.execute(
        select(SystemConfigAuditLog)
        .where(SystemConfigAuditLog.config_key == config_key)
        .order_by(SystemConfigAuditLog.created_at.desc())
    ).scalars().all()
    version = current.version
    for log in logs:
        if version == target_version:
            return log.new_value
        version -= 1
        if version == target_version:
            return log.old_value
    return None
```

Zero migrations. Zero model changes. If column-based versioning becomes necessary later (multi-key configs, concurrent writers), it can be added then.

**Decision: Use audit log scan for V1.3. Revisit if config complexity grows.**

### Issue 1: Config validation — addendum

Both the original review and Codex agree: validate on write path only. I want to add one clarification:

**Read path should still validate, but catch and log warning instead of raising.** This gives ops visibility into config drift without breaking webhook flow:

```python
def get_signal_bot_config(self) -> dict:
    # ... existing merge logic ...
    try:
        validate_signal_bot_config(merged_config)
    except ConfigValidationError as exc:
        logger.warning("signal_bot_config_validation_warning", extra={"error": str(exc)})
    return merged_config
```

Skipping validation entirely on reads means an admin could push a bad config through a raw DB patch and not discover it until they try `dry-run` — which could be days later. A warning log closes that gap.

**Decision: Write path raises. Read path catches + warns.**

---

## Agreed Final Decisions

| Issue | Decision | Owner |
|-------|----------|-------|
| #1 Config validation | Write path: raise. Read path: catch + log warning. | Plan Task 2 Step 5 |
| #2 Snapshot query | `ORDER BY bar_time DESC LIMIT 1` within tolerance window. No 2-query. | Plan Task 5 Step 2 |
| #3 Import chain | Update `market_context_service.py` import to `filter_rules.types` in Task 1. | Plan Task 1 Step 7 |
| #4 Rollback | Audit log scan, no migration. Revisit if config complexity grows. | Plan Task 8 Step 4 |
| Minor: Task 1 verification | Run full `python -m pytest tests/unit -q` after refactor. | Plan Task 1 Step 8 |
| Minor: Task 3 dead code | Explicitly remove inline SQL from controller. | Plan Task 3 Step 3 |
| Minor: Task 4 duplicate classes | Remove `_Noop*` from CLI after service extraction. | Plan Task 4 Step 4 |
| Minor: Task 7 contract | Document that proposals read current values from live config. | Plan Task 7 Step 2 |

---

## Codex Follow-Up On Claude Response

Reviewed again against the current code in:

- `app/repositories/config_repo.py`
- `app/repositories/market_context_repo.py`
- `app/services/market_context_service.py`
- `app/domain/models.py`

### Agreement

I still agree with:

- Issue 1 final decision: write path raises, read path catches and logs warning.
- Issue 3 final decision: move `FilterResult` import in `market_context_service.py` to `filter_rules.types`.
- All 4 minor fixes.

### Remaining Pushback

#### Issue 2: `ORDER BY bar_time DESC LIMIT 1` inside a symmetric window does not fully resolve the semantic concern

I agree this query shape is better than the original expression sort from a PostgreSQL/index perspective.

I do **not** agree that this completely settles the product semantic. With a symmetric tolerance window:

```sql
bar_time >= lower
bar_time <= upper
ORDER BY bar_time DESC
LIMIT 1
```

the query can still select a snapshot **after** the target `bar_time`. That matters because the question Claude states is:

> "what was the backend's regime view when this bar closed?"

If that is truly the question, then "latest snapshot in the symmetric window" is not identical to "state at close." A future snapshot may be the newest row in the window while still being unavailable at close time.

So I think one of these needs to be made explicit in the plan:

1. use `snapshot.bar_time <= target_bar_time` semantics and prefer the latest snapshot at or before close; or
2. keep the symmetric window but explicitly document that future snapshots are acceptable evidence for this advisory check.

My objection is not about performance anymore. It is about locking the business meaning clearly before implementation.

#### Issue 4: audit-log scan is acceptable, but still weaker than explicit version columns

I agree the audit-scan approach is viable for V1.3. I do **not** agree it is the cleaner invariant.

What the scan approach relies on:

- `SystemConfig.version` increments exactly by 1;
- every config mutation goes through `update_config_with_audit()`;
- audit ordering is sufficient to reconstruct history;
- no missing historical rows exist for the target config key.

Given the current code, these assumptions are mostly reasonable. They are still assumptions, not persisted version metadata.

Why I still prefer explicit `old_version/new_version`:

1. rollback becomes direct lookup, not reconstruction;
2. audit rows become self-describing;
3. reasoning about partial historical gaps is simpler;
4. future ops/debug work is easier.

So my position is:

- for a minimal V1.3 slice, audit-log scan is acceptable if we consciously accept weaker historical invariants;
- for the stronger design, schema-backed version columns are still preferable.

### Updated Codex Bottom Line

If the goal is minimum-change V1.3, Claude's final decisions are implementable.

If the goal is tighter correctness and clearer semantics, I would still adjust two points:

1. for snapshot lookup, avoid silently treating "latest row in symmetric window" as equivalent to "backend state at close";
2. for rollback, prefer explicit version metadata if we want the audit trail itself to be authoritative rather than reconstructed.

---

## Claude Final Response

### Issue 2: Accepted — asymmetric window

Codex is right. A symmetric window `[lower, upper]` can return a snapshot with `bar_time` after the target, meaning a snapshot that did not exist when the candle closed. That violates the intended semantic ("what was the backend's regime view when this bar closed?").

**Updated decision:** Use an asymmetric window `[lower, target_bar_time]` instead of `[lower, upper]`:

```python
stmt = (
    select(MarketContextSnapshot)
    .where(MarketContextSnapshot.symbol == symbol)
    .where(MarketContextSnapshot.timeframe == timeframe)
    .where(MarketContextSnapshot.bar_time >= lower)
    .where(MarketContextSnapshot.bar_time <= bar_time)  # not upper
    .order_by(MarketContextSnapshot.bar_time.desc())
    .limit(1)
)
if source is not None:
    stmt = stmt.where(MarketContextSnapshot.source == source)
```

This returns the most recent snapshot at or before the candle close, within the `snapshot_max_age_minutes` tolerance. Index `(symbol, timeframe, source, bar_time DESC)` supports this efficiently.

### Issue 4: No change — audit scan for V1.3

Codex acknowledges audit scan is acceptable for V1.3. Decision stands. If config complexity grows (multi-key, concurrent writers), we add version columns then.

---

## Final Decisions (Revised)

| Issue | Decision | Plan Step |
|-------|----------|-----------|
| #1 Config validation | Write path: raise. Read path: catch + log warning. | Task 2 Step 5 |
| #2 Snapshot query | `WHERE bar_time >= lower AND bar_time <= target` + `ORDER BY bar_time DESC LIMIT 1`. Asymmetric window. | Task 5 Step 2 |
| #3 Import chain | Update `market_context_service.py` import to `filter_rules.types` in Task 1. | Task 1 Step 7 |
| #4 Rollback | Audit log scan, no migration. Revisit if config complexity grows. | Task 8 Step 4 |
| Minor: Task 1 verification | Run full `python -m pytest tests/unit -q` after refactor. | Task 1 Step 8 |
| Minor: Task 3 dead code | Explicitly remove inline SQL from controller. | Task 3 Step 3 |
| Minor: Task 4 duplicate classes | Remove `_Noop*` from CLI after service extraction. | Task 4 Step 4 |
| Minor: Task 7 contract | Document that proposals read current values from live config. | Task 7 Step 2 |

**Status: All issues resolved. Plan ready for execution after incorporating these decisions.**
