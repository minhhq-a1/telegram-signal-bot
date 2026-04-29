# Post V1.1 Optimization Plan

Context for Claude Opus 4.6 / coding agents after PR #26 was merged into `main`.

## Current State

- Project: Telegram Signal Bot V1/V1.1.
- Latest merged PR: PR #26, V1.1 strategy validation, backend rescoring, reverify endpoint, reject analytics.
- `main` CI/CD after merge: passing.
- Local unit test status at review time: `125 passed`.

## Non-Negotiable Project Invariants

Do not violate these rules in any task:

1. Persist before notify: do not send Telegram before DB commit.
2. Idempotency: existing `signal_id` returns `200 DUPLICATE`, no duplicate insert.
3. Audit-first: every webhook logs to `webhook_events`, including invalid requests.
4. Config from DB/default config: do not introduce hardcoded operational thresholds outside config/migrations.
5. No secret logging: never log `TRADINGVIEW_SHARED_SECRET`, payload `secret`, Telegram token, auth headers, or dashboard token.
6. Boolean Gate routing:
   - Any `FAIL` -> `REJECT`, route `NONE`.
   - Any `WARN` with severity `MEDIUM` or `HIGH` -> `PASS_WARNING`, route `WARN`.
   - Otherwise -> `PASS_MAIN`, route `MAIN`.
7. SQLAlchemy 2.0 style: use `select()`, do not use `db.query()` in app code.
8. Python 3.12 type hints: use `str | None`, not `Optional[str]`.
9. Timestamps: use `datetime.now(timezone.utc)`.
10. UUIDs: generate in Python layer with `str(uuid.uuid4())`.

## Suggested Execution Order

Phase A - Low Risk Cleanup

1. Task 1.1 - Type hints cleanup.
2. Task 1.2 - Import/style cleanup.
3. Task 8.1 - Make targets.
4. Task 8.2 - Migration fixture regression.

Phase B - Performance & Query Safety

5. Task 2.1 - Duplicate query SQL range.
6. Task 2.2 - DB index migration.

Phase C - Maintainability Refactor

7. Task 3.1 - Extract routing.
8. Task 3.2 - Extract filter types.
9. Task 3.3 - Split rule modules.

Phase D - UX/Operations

10. Task 5.1 - Relax reverify required fields.
11. Task 5.2 - Reverify history endpoint.
12. Task 6.1 - Pipeline summary log.
13. Task 6.2 - Request correlation ID.
14. Task 7.1 - Reuse Telegram httpx client.
15. Task 4.1 - Analytics response schemas.
16. Task 4.2 - Analytics summary maintainability/performance.

---

# Epic 1 - Cleanup & Type Hint Hygiene

## Task 1.1 - Standardize Python 3.12 Type Hints

### Goal

Remove `Optional[...]` from app code and replace it with `T | None`, following project coding rules.

### Scope

Expected files:

- `app/services/auth_service.py`
- `app/services/filter_engine.py`
- `app/services/telegram_notifier.py`
- Any other `app/` file where `Optional[...]` appears.

### Technical Requirements

- No behavior change.
- No public API change.
- No test changes unless imports/types require it.

### Spec

Before:

```python
from typing import Optional

def validate_secret(secret: Optional[str]) -> bool:
    ...
```

After:

```python
def validate_secret(secret: str | None) -> bool:
    ...
```

Also update examples such as:

```python
details: dict | None = None
async def notify(...) -> tuple[str, dict | None, str | None]:
```

### Test Cases

Run:

```bash
python -m pytest tests/unit/test_auth_service.py -q
python -m pytest tests/unit/test_filter_engine.py -q
python -m pytest tests/unit/test_telegram_notifier.py -q
python -m pytest tests/unit -q
```

### Definition of Done

- `rg "Optional\\[" app` returns no results.
- Unit suite passes.
- No behavior diff beyond type/import cleanup.

---

## Task 1.2 - Remove Stale Imports and Minor Style Debt

### Goal

Clean up leftover refactor noise after V1.1.

### Scope

Expected files:

- `app/api/analytics_controller.py`
- `app/repositories/signal_repo.py`
- `app/services/filter_engine.py`

### Technical Requirements

- Remove unused import in `analytics_controller.py`:
  - `from sqlalchemy.orm import aliased` inside reject-stats function.
- Fix indentation in `SignalRepository.create()` for:
  - `squeeze_on`
  - `squeeze_fired`
  - `squeeze_bars`
  - `mom_direction`
  - `payload_timestamp`
- Remove stale imports after Task 1.1 if any.
- Do not change behavior.

### Test Cases

Run:

```bash
python -m pytest tests/unit -q
```

If DB is available:

```bash
python -m pytest tests/integration/test_api_regressions.py -q
```

### Definition of Done

- No obvious unused imports in changed files.
- No weird indentation in `signal_repo.py`.
- CI passes.

---

# Epic 2 - Repository Query Optimization

## Task 2.1 - Push Duplicate Price Tolerance Filtering Down to SQL

### Goal

Optimize `DUPLICATE_SUPPRESSION` by letting Postgres filter candidates by entry-price range instead of loading all recent candidates and looping in Python.

### Current Behavior

`SignalRepository.find_recent_similar()` filters by:

- symbol
- timeframe
- side
- created_at window
- optional signal_type

Then `FilterEngine._check_duplicate()` loops in Python:

```python
abs(entry - float(cand.entry_price)) / float(cand.entry_price) < tolerance
```

### Scope

Files:

- `app/repositories/signal_repo.py`
- `app/services/filter_engine.py`
- `tests/integration/test_signal_repository.py`
- `tests/unit/test_filter_engine.py` if mocks/signatures need updates.

### Spec

Add a new repository method instead of changing the old one abruptly:

```python
def find_recent_similar_by_entry_range(
    self,
    symbol: str,
    timeframe: str,
    side: str,
    signal_type: str | None,
    entry_price: float,
    tolerance_pct: float,
    since_minutes: int,
    exclude_signal_id: str | None = None,
) -> list[Signal]:
    ...
```

Use a SQL range equivalent to the old behavior. Old condition:

```python
abs(entry - cand_entry) / cand_entry < tolerance
```

Equivalent range:

```python
lower = entry_price / (1 + tolerance_pct)
upper = entry_price / (1 - tolerance_pct)
```

SQL conditions:

```python
Signal.symbol == symbol
Signal.timeframe == timeframe
Signal.side == side
Signal.created_at >= since
Signal.entry_price > lower
Signal.entry_price < upper
```

Signal type behavior:

- If `signal_type is not None`, filter `Signal.signal_type == signal_type`.
- If `signal_type is None`, do not filter signal type, preserving current behavior.

Update `FilterEngine._check_duplicate()` to call this new method. It should only check if any candidates exist; no Python price loop should be needed.

### Test Cases

Integration repository tests:

1. `find_recent_similar_by_entry_range_returns_candidate_within_tolerance`
   - Existing entry `100`.
   - New entry `100.1`.
   - Tolerance `0.002`.
   - Candidate found.

2. `find_recent_similar_by_entry_range_excludes_outside_tolerance`
   - Existing entry `100`.
   - New entry `101`.
   - Tolerance `0.002`.
   - No candidate.

3. `find_recent_similar_by_entry_range_respects_signal_type`
   - Same symbol/timeframe/side/entry, different `signal_type`.
   - Only matching signal_type returned.

4. `find_recent_similar_by_entry_range_excludes_signal_id`
   - Existing row has same `signal_id` as exclude.
   - No candidate.

Filter engine tests:

5. Duplicate inside tolerance -> `DUPLICATE_SUPPRESSION` FAIL.
6. Duplicate outside tolerance -> `DUPLICATE_SUPPRESSION` PASS.

### Definition of Done

- Duplicate behavior remains compatible with existing tests.
- New repository tests pass.
- `_check_duplicate()` no longer does broad candidate price loop.
- CI passes.

---

## Task 2.2 - Add DB Index for Duplicate/Cooldown Query Patterns

### Goal

Improve query performance for duplicate and cooldown checks.

### Scope

Files:

- New migration: `migrations/004_query_indexes.sql`
- `docs/DATABASE_SCHEMA.md` if index docs are maintained there.
- `tests/integration/test_ci_migration_fixture.py` expected migration list.

### Spec

Add idempotent raw SQL migration:

```sql
CREATE INDEX IF NOT EXISTS idx_signals_dup_lookup
ON signals(symbol, timeframe, side, signal_type, created_at DESC, entry_price);
```

Rationale:

- Duplicate check uses symbol/timeframe/side/signal_type/created_at/entry_price.
- Cooldown uses symbol/timeframe/side/created_at and joins decisions.

Only add more indexes if query plan or tests justify it.

### Test Cases

- Migration apply on empty DB.
- Migration run twice without error.
- Update `tests/integration/test_ci_migration_fixture.py` to expect migration `004`.

### Definition of Done

- New migration appears in migration runner status.
- Restore drill passes.
- CI passes.

---

# Epic 3 - Filter Engine Maintainability

## Task 3.1 - Extract Boolean Gate Routing Logic

### Goal

Protect the routing invariant by moving it into dedicated, focused code with dedicated tests.

### Scope

Files:

- New file: `app/services/filter_routing.py`
- Maybe new file: `app/services/filter_types.py` if needed to avoid circular imports.
- `app/services/filter_engine.py`
- New tests: `tests/unit/test_filter_routing.py`

### Spec

Create:

```python
from app.core.enums import DecisionType, TelegramRoute, RuleResult, RuleSeverity
from app.services.filter_types import FilterResult


def decide_route(results: list[FilterResult]) -> tuple[DecisionType, TelegramRoute]:
    if any(r.result == RuleResult.FAIL for r in results):
        return DecisionType.REJECT, TelegramRoute.NONE

    if any(
        r.result == RuleResult.WARN
        and r.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
        for r in results
    ):
        return DecisionType.PASS_WARNING, TelegramRoute.WARN

    return DecisionType.PASS_MAIN, TelegramRoute.MAIN
```

If importing `FilterResult` from `filter_engine.py` creates circular imports, do Task 3.2 first or create `filter_types.py` in the same PR.

Update `FilterEngine._decide()` to delegate to `decide_route()` or remove `_decide()`.

### Test Cases

`tests/unit/test_filter_routing.py`:

1. No FAIL and no MEDIUM/HIGH WARN -> `PASS_MAIN`, `MAIN`.
2. LOW WARN only -> `PASS_MAIN`, `MAIN`.
3. MEDIUM WARN -> `PASS_WARNING`, `WARN`.
4. HIGH WARN -> `PASS_WARNING`, `WARN`.
5. FAIL plus warnings -> `REJECT`, `NONE`.
6. Multiple mixed results preserve FAIL priority.

### Definition of Done

- Boolean Gate has dedicated tests.
- `FilterEngine` uses extracted routing.
- Existing filter engine tests pass.
- CI passes.

---

## Task 3.2 - Extract Filter Dataclasses to `filter_types.py`

### Goal

Reduce circular import risk and prepare for rule module split.

### Scope

Files:

- New file: `app/services/filter_types.py`
- Update:
  - `app/services/filter_engine.py`
  - `app/services/strategy_validator.py`
  - tests importing `FilterResult` or `FilterExecutionResult`

### Spec

Move these dataclasses to `filter_types.py`:

```python
@dataclasses.dataclass
class FilterResult:
    ...

@dataclasses.dataclass
class FilterExecutionResult:
    ...
```

Keep `FilterResult.to_dict()` behavior unchanged.

Compatibility option:

```python
# app/services/filter_engine.py
from app.services.filter_types import FilterResult, FilterExecutionResult
```

Tests/code should gradually import from `filter_types.py`.

### Test Cases

Run:

```bash
python -m pytest tests/unit/test_filter_engine.py -q
python -m pytest tests/unit/test_strategy_validator.py -q
python -m pytest tests/integration/test_signal_reverify.py -q
```

### Definition of Done

- No duplicate dataclass definitions.
- No circular imports.
- Existing behavior unchanged.
- CI passes.

---

## Task 3.3 - Split Rule Groups into Modules

### Goal

Make `FilterEngine` an orchestrator instead of a large class containing every rule implementation.

### Scope

New files:

- `app/services/rules/__init__.py`
- `app/services/rules/validation_rules.py`
- `app/services/rules/trade_math_rules.py`
- `app/services/rules/business_rules.py`
- `app/services/rules/advisory_rules.py`
- `app/services/rules/v11_rules.py`

Update:

- `app/services/filter_engine.py`

### Spec

Move rule functions into modules as functions returning `FilterResult` or list of `FilterResult`.

Examples:

```python
def check_symbol(signal: dict, config: dict) -> FilterResult:
    ...


def check_duplicate(signal: dict, config: dict, signal_repo: Any) -> FilterResult:
    ...


def check_news_block(signal: dict, config: dict, market_event_repo: Any) -> FilterResult | None:
    ...
```

`FilterEngine.run()` should keep the exact existing phase order and short-circuit behavior:

1. Hard validation.
2. Trade math.
3. Strategy-specific validation.
4. Hard business rules.
5. Advisory warnings.
6. RR profile match.
7. Backend rescoring.
8. Routing.

Behavior must remain identical:

- Rule order unchanged.
- Short-circuit points unchanged.
- Decision reason unchanged unless tests explicitly update and verify.
- `server_score` calculation unchanged.

### Test Cases

- Existing `tests/unit/test_filter_engine.py` pass.
- Existing `tests/unit/test_strategy_validator.py` pass.
- Existing webhook integration tests pass in CI.

### Definition of Done

- `filter_engine.py` is significantly smaller and mostly orchestrates.
- Rule modules have focused logic.
- CI passes.

---

# Epic 4 - Analytics API Contract & Performance

## Task 4.1 - Add Pydantic Response Schemas for Analytics

### Goal

Make analytics API contracts explicit and improve OpenAPI docs.

### Scope

Files:

- `app/domain/schemas.py` or new `app/domain/analytics_schemas.py`
- `app/api/analytics_controller.py`
- `tests/integration/test_analytics.py`
- `tests/integration/test_analytics_reject_stats.py`

### Spec

Add response models such as:

```python
class AnalyticsSummaryResponse(BaseModel):
    period_days: int
    total_signals: int
    decisions: dict[str, int]
    telegram_delivery: dict[str, int]
    by_side: dict[str, int]
    by_symbol: dict[str, int]
    by_timeframe: dict[str, int]
    by_strategy: dict[str, int]
    avg_confidence: float
    avg_server_score: float
```

Also define:

- `SignalTimelineResponse`
- `FilterStatsResponse`
- `DailyBreakdownResponse`
- `RejectStatsResponse`

Add `response_model=` to analytics routes.

### Test Cases

1. Existing analytics integration tests pass.
2. Response JSON shape remains unchanged.
3. `app.openapi()` generation succeeds.

### Definition of Done

- All analytics endpoints have response models.
- No response contract break.
- CI passes.

---

## Task 4.2 - Improve `/analytics/summary` Maintainability and Query Efficiency

### Goal

Reduce duplication and prepare summary endpoint for larger data volumes.

### Scope

Files:

- `app/api/analytics_controller.py`
- `tests/integration/test_analytics.py`

### Spec

At minimum, add helper(s) to reduce repeated count-by code:

```python
def _count_by(db: Session, column: Any, since: datetime, limit: int | None = None) -> dict[str, int]:
    ...
```

Do not make SQL unreadable just to reduce query count. Safe maintainability improvement is acceptable.

Optional: combine some aggregates using conditional aggregation if clear.

### Test Cases

- Existing summary tests pass.
- Empty DB returns zero/empty values as before.
- Null strategy maps to `UNKNOWN`.

### Definition of Done

- Response unchanged.
- Code duplication reduced.
- CI passes.

---

# Epic 5 - Reverify UX & Legacy Compatibility

## Task 5.1 - Relax Reverify Required Fields for Legacy Signals

### Goal

Allow reverify of legacy signals that lack `signal_type` or `strategy`, as long as core trade fields are present.

### Current Behavior

`reverify_signal()` requires:

```python
("entry_price", "risk_reward", "indicator_confidence", "signal_type", "strategy")
```

### Desired Behavior

Require only trade-critical fields:

```python
required = (
    "price",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "indicator_confidence",
)
```

`signal_type` and `strategy` should be optional. If missing, strategy validator skips strategy-specific checks naturally.

### Scope

Files:

- `app/api/signal_controller.py`
- `tests/integration/test_signal_reverify.py`
- Optional docs update in `docs/API_REFERENCE.md`

### Test Cases

1. Invalid/legacy `raw_payload`, missing `strategy`, enough trade fields:
   - `POST /api/v1/signals/{signal_id}/reverify` returns `200`.
   - Response includes `reverify_decision`.

2. Missing `risk_reward`:
   - returns `422`.
   - `detail.reason == "missing_required_persisted_fields"`.
   - `risk_reward` appears in missing fields.

3. Missing `stop_loss`:
   - returns `422`.

4. Existing reverify tests pass.

### Definition of Done

- Legacy persisted snapshots can reverify core filters.
- Missing trade-critical fields still return explicit 422.
- CI passes.

---

## Task 5.2 - Add Reverify History Endpoint

### Goal

Expose persisted `signal_reverify_results` audit history.

### Endpoint

```http
GET /api/v1/signals/{signal_id}/reverify-results
```

Auth:

- Same dashboard auth as signal detail/reverify.

Response shape:

```json
{
  "signal_id": "...",
  "count": 2,
  "results": [
    {
      "id": "...",
      "original_decision": "PASS_MAIN",
      "reverify_decision": "PASS_WARNING",
      "reverify_score": 72,
      "reject_code": null,
      "decision_reason": "...",
      "created_at": "..."
    }
  ]
}
```

### Scope

Files:

- `app/api/signal_controller.py`
- schemas
- `tests/integration/test_signal_reverify.py`

### Test Cases

1. Unknown signal -> `404`.
2. Signal with no reverify results -> `200`, count `0`.
3. Multiple results -> newest first.
4. Auth required.

### Definition of Done

- Endpoint documented by OpenAPI schema.
- Integration tests pass.
- Original signal is not mutated.

---

# Epic 6 - Observability

## Task 6.1 - Add Structured Pipeline Summary Log

### Goal

Emit a single structured log event summarizing each valid signal's filter pipeline result.

### Scope

Files:

- `app/services/webhook_ingestion_service.py`
- `tests/unit/test_logging.py` or new unit test

### Spec

After `filter_result` is built and before/after decision insert, emit:

```python
logger.info(
    "signal_filter_pipeline_completed",
    extra={
        "signal_id": norm_data["signal_id"],
        "decision": filter_result.final_decision.value,
        "route": filter_result.route.value,
        "server_score": filter_result.server_score,
        "fail_codes": [r.rule_code for r in filter_result.filter_results if r.result.value == "FAIL"],
        "warn_codes": [r.rule_code for r in filter_result.filter_results if r.result.value == "WARN"],
    },
)
```

Optional duration:

```python
started = time.perf_counter()
duration_ms = round((time.perf_counter() - started) * 1000, 2)
```

Do not log secrets or raw payload.

### Test Cases

1. Use `caplog` to assert event name exists.
2. Assert decision/route present.
3. Assert secret value does not appear in log text.

### Definition of Done

- Structured summary log emitted for valid authenticated non-duplicate signal.
- No secret leakage.
- Tests pass.

---

## Task 6.2 - Add Request Correlation ID

### Goal

Make it easier to trace one webhook through logs.

### Scope

Files:

- `app/api/webhook_controller.py` or `WebhookIngestionService`
- logging helpers if needed
- tests

### Spec

Lower-risk implementation: log-only correlation ID, no DB schema change.

- Accept `X-Request-ID` if present and reasonable length.
- If missing or too long, generate `str(uuid.uuid4())`.
- Include `request_id` in key webhook pipeline logs via `extra={"request_id": request_id}`.

### Test Cases

1. Request with `X-Request-ID` logs that value.
2. Request without header logs a generated UUID-like value.
3. Too-long header is ignored/replaced.

### Definition of Done

- Logs can correlate one request.
- No DB migration unless explicitly chosen.
- Tests pass.

---

# Epic 7 - Telegram Client Lifecycle

## Task 7.1 - Support Reusing `httpx.AsyncClient` in TelegramNotifier

### Goal

Avoid creating a new HTTP client per Telegram message and make tests easier.

### Scope

Files:

- `app/services/telegram_notifier.py`
- tests for notifier

### Spec: Minimal Low-Risk Version

Allow dependency injection:

```python
class TelegramNotifier:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.bot_token = settings.telegram_bot_token
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self._client = client
```

`send_message()` behavior:

- If `_client` is provided, use it and do not close it.
- Else keep current behavior with `async with httpx.AsyncClient(timeout=10.0) as client:`.

Do not add FastAPI lifespan unless necessary.

### Test Cases

1. Existing notifier tests pass.
2. Injected fake/mock client is used.
3. 429 retry behavior still works.
4. Permanent 4xx still raises/no retry.

### Definition of Done

- No behavior change for existing call sites.
- Client injection supported.
- Tests pass.

---

# Epic 8 - CI and Local Developer Experience

## Task 8.1 - Add Make Targets for Common Checks

### Goal

Make local test/migration commands discoverable and reduce CI-only surprises.

### Scope

Files:

- `Makefile`
- `README.md` or `docs/LOCAL_SMOKE_CHECKLIST.md`

### Spec

Add targets:

```make
test-unit:
	./.venv/bin/python -m pytest tests/unit -q

test-integration:
	./.venv/bin/python -m pytest tests/integration -q

migration-status:
	./.venv/bin/python scripts/db/migrate.py status

migration-apply:
	./.venv/bin/python scripts/db/migrate.py apply

ci-local:
	./.venv/bin/python -m pytest -q
```

Document that integration tests skip if `INTEGRATION_DATABASE_URL` is not set.

### Test Cases

Manual:

```bash
make test-unit
```

If DB env is available:

```bash
make migration-status
make test-integration
```

### Definition of Done

- Make targets documented.
- Existing targets not broken.
- Unit tests pass.

---

## Task 8.2 - Strengthen Migration Fixture Regression Tests

### Goal

Ensure integration fixture keeps using raw migrations and never regresses to ORM-only `create_all()` without seed data.

### Scope

Files:

- `tests/integration/test_ci_migration_fixture.py`
- Maybe `tests/integration/conftest.py`

### Spec

Add or strengthen assertions:

```python
def test_db_fixture_has_schema_migrations_rows(db_session):
    rows = db_session.execute(
        text("SELECT version, filename FROM schema_migrations ORDER BY version")
    ).all()
    assert len(rows) >= 3
```

Also assert V1.1 config keys exist:

```python
assert "rescoring" in config
assert "strategy_thresholds" in config
assert "rr_target_by_type" in config
```

### Test Cases

Run in CI with Postgres:

```bash
python -m pytest tests/integration/test_ci_migration_fixture.py -q
```

### Definition of Done

- Fixture regression catches missing raw migration seed.
- CI passes.

---

# Merge Gate for Every PR

Each PR should include:

1. Clear PR description:
   - Scope.
   - Behavior change: yes/no.
   - Tests run.
   - Migration impact if any.

2. Required checks:

```bash
python -m pytest tests/unit -q
```

3. If DB/migration/API behavior changed, CI integration tests must pass.

4. No violations:
   - No `db.query()`.
   - No `Optional[...]` in app after Task 1.1.
   - No new hardcoded thresholds outside config/default/migration.
   - No Telegram notify before DB commit.
   - No secret logs.
   - Boolean Gate unchanged.

5. GitHub CI must pass:
   - `test`
   - `restore-drill`
   - `docker-build`

---

# Prompt Template for Claude Opus 4.6

Use this prompt for each task:

```text
Bạn đang làm trong repo telegram-signal-bot. Hãy đọc AGENTS.md và docs/FILTER_RULES.md trước.

Nhiệm vụ: <paste Task X.Y from docs/POST_V11_OPTIMIZATION_PLAN.md here>.

Ràng buộc:
- Không đổi behavior ngoài scope task.
- Không vi phạm Boolean Gate: FAIL -> REJECT, WARN MEDIUM+ -> PASS_WARNING, else PASS_MAIN.
- Persist trước notify sau.
- Không log secret.
- SQLAlchemy dùng select(), không dùng db.query().
- Type hints dùng `str | None`, không dùng `Optional[str]`.
- Nếu có migration, tạo raw SQL migration mới, idempotent, và update tests.
- Chạy tests liên quan và báo kết quả.

Deliverables:
- Code changes theo scope.
- Tests mới/cập nhật theo test cases.
- Summary ngắn + test commands đã chạy.
- Nếu không chạy được test nào, nêu lý do rõ.
```
