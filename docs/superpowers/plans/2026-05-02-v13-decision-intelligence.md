# V1.3 Decision Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V1.3 Decision Intelligence: service-boundary cleanup, market context advisory routing, calibration proposals, reviewed config changes, replay impact comparison, and dashboard/docs release hardening.

**Architecture:** Keep the existing webhook and boolean gate contracts stable while extracting focused services around filter rules, config validation, calibration, and replay. New decision-intelligence features stay advisory and manually reviewed; no auto-trade and no automatic live config mutation.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 `select()`, Pydantic v2, PostgreSQL 16 raw SQL migrations, httpx async, pytest.

---

## Source Spec

- Roadmap: `docs/ROADMAP_V1.3.md`
- Core invariants: `AGENTS.md`, `docs/FILTER_RULES.md`, `docs/PAYLOAD_CONTRACT.md`
- Current release context: `docs/RELEASE_V12_HANDOFF.md`

## Scope Check

The roadmap spans multiple subsystems, so this plan is sliced into PR-sized tasks. Each task should be implemented, tested, and committed independently. Do not batch several tasks into one commit.

## File Map

Create:

- `app/services/filter_rules/__init__.py` - package marker and shared exports.
- `app/services/filter_rules/types.py` - `FilterResult`, `FilterExecutionResult`, helper predicates.
- `app/services/filter_rules/validation.py` - symbol/timeframe/confidence/price checks.
- `app/services/filter_rules/trade_math.py` - direction sanity and RR checks.
- `app/services/filter_rules/business.py` - confidence threshold, duplicate, news, regime hard block.
- `app/services/filter_rules/advisory.py` - volatility, cooldown, low volume, RR profile, backend score.
- `app/services/filter_rules/market_context.py` - market context rule adapter.
- `app/services/filter_rules/routing.py` - boolean gate route/decision helpers.
- `app/services/config_validation.py` - Pydantic v2 validation for `signal_bot_config`.
- `app/services/calibration_proposals.py` - proposal builder and guardrails.
- `app/services/replay_service.py` - reusable replay and compare engine.
- `migrations/010_v13_market_context_index.sql` - market context at-or-before-close lookup index.
- `tests/unit/test_config_validation.py`
- `tests/unit/test_filter_rule_modules.py`
- `tests/unit/test_calibration_proposals.py`
- `tests/unit/test_replay_service.py`
- `tests/integration/test_market_context_integration.py`
- `tests/integration/test_config_dry_run_rollback.py`
- `tests/integration/test_calibration_proposals_api.py`

Modify:

- `app/services/filter_engine.py` - orchestrator only; keep public API.
- `app/repositories/config_repo.py` - strict validation on write paths, warning-only validation on read paths, rollback lookup.
- `app/repositories/market_context_repo.py` - latest snapshot-at-or-before-close lookup.
- `app/services/market_context_service.py` - tolerate missing/stale context and source.
- `app/api/analytics_controller.py` - delegate calibration/proposal logic.
- `app/api/config_controller.py` - dry-run and rollback endpoints.
- `app/domain/schemas.py` - response/request models for proposals, dry-run, replay where needed.
- `scripts/replay_payloads.py` - thin CLI wrapper around `ReplayService`.
- `app/templates/dashboard.html` - Decision Intelligence panel.
- `migrations/008_v12_config_audit.sql` - do not edit; create new migration if schema is needed.
- `tests/integration/test_ci_migration_fixture.py` - include migration 010.
- `docs/API_REFERENCE.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/FILTER_RULES.md`
- `docs/QA_STRATEGY.md`
- `docs/VERSION_HISTORY.md`
- `docs/LOCAL_SMOKE_CHECKLIST.md`
- `docs/RELEASE_V13_HANDOFF.md`

---

## Task 0: Baseline Verification

**Files:**
- Read: `docs/ROADMAP_V1.3.md`
- Read: `app/services/filter_engine.py`
- Read: `app/api/analytics_controller.py`
- Read: `scripts/replay_payloads.py`

- [ ] **Step 1: Confirm branch and clean tracked state**

Run:

```bash
git status --short --branch
```

Expected:

```text
## release/1.3
```

Untracked plan files are acceptable. Tracked app files should be clean before code changes.

- [ ] **Step 2: Run filter baseline tests**

Run:

```bash
python -m pytest tests/unit/test_filter_engine.py -q
```

Expected: all selected tests pass. If this fails before edits, stop and investigate baseline drift before implementing Task 1.

- [ ] **Step 3: Run unit baseline**

Run:

```bash
python -m pytest tests/unit -q
```

Expected: unit suite passes.

- [ ] **Step 4: Record DB-dependent baseline when DB is available**

Run:

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  python -m pytest tests/integration -q
```

Expected when PostgreSQL is available: integration suite passes. If the env var is absent, note skipped DB verification in the task summary.

---

## Task 1: FilterEngine Boundary Refactor

**Files:**
- Create: `app/services/filter_rules/__init__.py`
- Create: `app/services/filter_rules/types.py`
- Create: `app/services/filter_rules/validation.py`
- Create: `app/services/filter_rules/trade_math.py`
- Create: `app/services/filter_rules/business.py`
- Create: `app/services/filter_rules/advisory.py`
- Create: `app/services/filter_rules/routing.py`
- Modify: `app/services/filter_engine.py`
- Modify: `app/services/market_context_service.py`
- Test: `tests/unit/test_filter_engine.py`
- Test: `tests/unit/test_filter_rule_modules.py`
- Test: `tests/unit/test_market_context_service.py`

- [ ] **Step 1: Add focused tests for extracted routing and validation helpers**

Create `tests/unit/test_filter_rule_modules.py`:

```python
from __future__ import annotations

from app.core.enums import DecisionType, RuleResult, RuleSeverity, TelegramRoute
from app.services.filter_rules.routing import decide, build_decision_reason
from app.services.filter_rules.types import FilterResult
from app.services.filter_rules.validation import check_symbol, check_timeframe


def test_decide_rejects_on_any_fail() -> None:
    results = [FilterResult("SYMBOL_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL)]

    decision, route = decide(results)

    assert decision == DecisionType.REJECT
    assert route == TelegramRoute.NONE


def test_decide_warns_on_medium_warn() -> None:
    results = [FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM)]

    decision, route = decide(results)

    assert decision == DecisionType.PASS_WARNING
    assert route == TelegramRoute.WARN


def test_decide_passes_main_on_low_warn_only() -> None:
    results = [FilterResult("VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW)]

    decision, route = decide(results)

    assert decision == DecisionType.PASS_MAIN
    assert route == TelegramRoute.MAIN


def test_build_decision_reason_lists_medium_warns_only_for_warning_route() -> None:
    results = [
        FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM),
        FilterResult("VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW),
    ]

    reason = build_decision_reason("Filters passed", results, DecisionType.PASS_WARNING)

    assert reason == "Warnings triggered: LOW_VOLUME_WARNING"


def test_validation_helpers_append_expected_results() -> None:
    results: list[FilterResult] = []
    config = {"allowed_symbols": ["BTCUSDT"], "allowed_timeframes": ["5m"]}
    signal = {"symbol": "ETHUSDT", "timeframe": "1h"}

    check_symbol(signal, config, results)
    check_timeframe(signal, config, results)

    assert [item.rule_code for item in results] == ["SYMBOL_ALLOWED", "TIMEFRAME_ALLOWED"]
    assert [item.result for item in results] == [RuleResult.FAIL, RuleResult.FAIL]
```

- [ ] **Step 2: Run new tests and verify they fail before extraction**

Run:

```bash
python -m pytest tests/unit/test_filter_rule_modules.py -q
```

Expected: import failure for `app.services.filter_rules`.

- [ ] **Step 3: Extract shared types**

Create `app/services/filter_rules/types.py`:

```python
from __future__ import annotations

import dataclasses

from app.core.enums import DecisionType, RuleResult, RuleSeverity, TelegramRoute


@dataclasses.dataclass
class FilterResult:
    rule_code: str
    rule_group: str
    result: RuleResult
    severity: RuleSeverity
    score_delta: float = 0.0
    details: dict | None = None

    def to_dict(self) -> dict:
        return {
            "rule_code": self.rule_code,
            "rule_group": self.rule_group,
            "result": self.result.value,
            "severity": self.severity.value,
            "score_delta": self.score_delta,
            "details": self.details,
        }


@dataclasses.dataclass
class FilterExecutionResult:
    filter_results: list[FilterResult]
    server_score: float
    final_decision: DecisionType
    decision_reason: str
    route: TelegramRoute


def has_fail(results: list[FilterResult]) -> bool:
    return any(result.result == RuleResult.FAIL for result in results)
```

Create `app/services/filter_rules/__init__.py`:

```python
from __future__ import annotations

from app.services.filter_rules.types import FilterExecutionResult, FilterResult

__all__ = ["FilterExecutionResult", "FilterResult"]
```

- [ ] **Step 4: Extract routing helpers**

Create `app/services/filter_rules/routing.py`:

```python
from __future__ import annotations

from app.core.enums import DecisionType, RuleResult, RuleSeverity, TelegramRoute
from app.services.filter_rules.types import FilterResult


def decide(results: list[FilterResult]) -> tuple[DecisionType, TelegramRoute]:
    if any(result.result == RuleResult.FAIL for result in results):
        return DecisionType.REJECT, TelegramRoute.NONE

    significant_warns = [
        result
        for result in results
        if result.result == RuleResult.WARN
        and result.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
    ]
    if significant_warns:
        return DecisionType.PASS_WARNING, TelegramRoute.WARN

    return DecisionType.PASS_MAIN, TelegramRoute.MAIN


def build_decision_reason(
    phase_reason: str,
    results: list[FilterResult],
    decision: DecisionType,
) -> str:
    fail_codes = [result.rule_code for result in results if result.result == RuleResult.FAIL]
    medium_plus_warn_codes = [
        result.rule_code
        for result in results
        if result.result == RuleResult.WARN and result.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
    ]
    low_warn_codes = [
        result.rule_code
        for result in results
        if result.result == RuleResult.WARN and result.severity == RuleSeverity.LOW
    ]

    if decision == DecisionType.REJECT:
        return f"{phase_reason}: {', '.join(fail_codes)}"
    if decision == DecisionType.PASS_WARNING:
        return f"Warnings triggered: {', '.join(medium_plus_warn_codes)}"
    if low_warn_codes:
        return f"Passed main route with advisory warnings: {', '.join(low_warn_codes)}"
    return "Passed all filters"
```

- [ ] **Step 5: Extract validation rules**

Create `app/services/filter_rules/validation.py` by moving the existing logic from `FilterEngine._check_symbol`, `_check_timeframe`, `_check_confidence_range`, and `_check_price_valid` into functions with this shape:

```python
from __future__ import annotations

from app.core.enums import RuleResult, RuleSeverity
from app.services.filter_rules.types import FilterResult


def check_symbol(signal: dict, config: dict, results: list[FilterResult]) -> None:
    allowed = config.get("allowed_symbols", ["BTCUSDT", "BTCUSD"])
    if signal["symbol"] not in allowed:
        results.append(FilterResult("SYMBOL_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL, 0.0, {"allowed": allowed}))
    else:
        results.append(FilterResult("SYMBOL_ALLOWED", "validation", RuleResult.PASS, RuleSeverity.INFO))


def check_timeframe(signal: dict, config: dict, results: list[FilterResult]) -> None:
    allowed = config.get("allowed_timeframes", ["1m", "3m", "5m", "12m", "15m", "30m", "1h"])
    if signal["timeframe"] not in allowed:
        results.append(FilterResult("TIMEFRAME_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL, 0.0, {"allowed": allowed}))
    else:
        results.append(FilterResult("TIMEFRAME_ALLOWED", "validation", RuleResult.PASS, RuleSeverity.INFO))


def check_confidence_range(signal: dict, results: list[FilterResult]) -> None:
    confidence = signal.get("indicator_confidence", -1)
    if 0.0 <= confidence <= 1.0:
        results.append(FilterResult("CONFIDENCE_RANGE_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO))
    else:
        results.append(FilterResult("CONFIDENCE_RANGE_VALID", "validation", RuleResult.FAIL, RuleSeverity.HIGH, 0.0, {"confidence": confidence}))


def check_price_valid(signal: dict, results: list[FilterResult]) -> None:
    price = signal.get("price", 0)
    entry = signal.get("entry_price", 0)
    stop_loss = signal.get("stop_loss") or 0
    take_profit = signal.get("take_profit") or 0
    if price > 0 and entry > 0 and stop_loss > 0 and take_profit > 0:
        results.append(FilterResult("PRICE_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO))
    else:
        results.append(FilterResult("PRICE_VALID", "validation", RuleResult.FAIL, RuleSeverity.HIGH))
```

- [ ] **Step 6: Extract remaining rule groups without changing behavior**

Move method bodies from `app/services/filter_engine.py` into:

- `app/services/filter_rules/trade_math.py`: `check_direction_sanity(signal, results)`, `check_min_rr(signal, config, results)`
- `app/services/filter_rules/business.py`: `check_min_confidence_by_tf(signal, config, results)`, `check_duplicate(signal, config, signal_repo, results)`, `check_news_block(signal, config, market_event_repo, results)`, `check_regime_hard_block(signal, results)`
- `app/services/filter_rules/advisory.py`: `check_volatility(signal, results)`, `check_cooldown(signal, config, signal_repo, results)`, `check_low_volume(signal, results)`, `check_rr_profile_match(signal, config, results)`, `check_backend_score(signal, config, results)`

Keep the same rule codes, severity, score deltas, details, defaults, and imports used by the current methods.

- [ ] **Step 7: Make `FilterEngine` an orchestrator**

Modify `app/services/filter_engine.py` so it imports the extracted functions, re-exports `FilterResult` and `FilterExecutionResult`, and keeps `run()` order identical:

```python
from __future__ import annotations

from typing import Any

from app.services.filter_rules import FilterExecutionResult, FilterResult
from app.services.filter_rules.advisory import (
    check_backend_score,
    check_cooldown,
    check_low_volume,
    check_rr_profile_match,
    check_volatility,
)
from app.services.filter_rules.business import (
    check_duplicate,
    check_min_confidence_by_tf,
    check_news_block,
    check_regime_hard_block,
)
from app.services.filter_rules.routing import build_decision_reason, decide
from app.services.filter_rules.trade_math import check_direction_sanity, check_min_rr
from app.services.filter_rules.types import has_fail
from app.services.filter_rules.validation import (
    check_confidence_range,
    check_price_valid,
    check_symbol,
    check_timeframe,
)


class FilterEngine:
    def __init__(self, config: dict, signal_repo: Any, market_event_repo: Any):
        self.config = config
        self.signal_repo = signal_repo
        self.market_event_repo = market_event_repo

    def run(self, signal: dict) -> FilterExecutionResult:
        results: list[FilterResult] = []

        check_symbol(signal, self.config, results)
        check_timeframe(signal, self.config, results)
        check_confidence_range(signal, results)
        check_price_valid(signal, results)
        if has_fail(results):
            return self._build_result(results, signal, "Hard validation failed")

        check_direction_sanity(signal, results)
        check_min_rr(signal, self.config, results)
        if has_fail(results):
            return self._build_result(results, signal, "Trade math failed")

        from app.services.strategy_validator import validate_strategy

        results.extend(validate_strategy(signal, self.config))
        if has_fail(results):
            return self._build_result(results, signal, "Strategy validation failed")

        check_min_confidence_by_tf(signal, self.config, results)
        check_duplicate(signal, self.config, self.signal_repo, results)
        check_news_block(signal, self.config, self.market_event_repo, results)
        check_regime_hard_block(signal, results)
        if has_fail(results):
            return self._build_result(results, signal, "Business rule failed")

        check_volatility(signal, results)
        check_cooldown(signal, self.config, self.signal_repo, results)
        check_low_volume(signal, results)
        check_rr_profile_match(signal, self.config, results)
        check_backend_score(signal, self.config, results)

        return self._build_result(results, signal, "Filters passed")

    def _build_result(self, results: list[FilterResult], signal: dict, reason: str) -> FilterExecutionResult:
        score = signal.get("indicator_confidence", 0.0)
        for result in results:
            score += result.score_delta
        score = max(0.0, min(1.0, score))

        decision, route = decide(results)
        decision_reason = build_decision_reason(reason, results, decision)
        return FilterExecutionResult(
            filter_results=results,
            server_score=round(score, 4),
            final_decision=decision,
            decision_reason=decision_reason,
            route=route,
        )
```

Also update `app/services/market_context_service.py` to import `FilterResult` directly from the extracted type module:

```python
from app.services.filter_rules.types import FilterResult
```

Remove the old import through `app.services.filter_engine`. This avoids a fragile import chain once `filter_rules/market_context.py` is introduced.

- [ ] **Step 8: Run characterization tests**

Run:

```bash
python -m pytest tests/unit/test_filter_rule_modules.py tests/unit/test_filter_engine.py -q
python -m pytest tests/unit/test_strategy_validator.py tests/unit/test_rescoring_engine.py -q
python -m pytest tests/unit/test_market_context_service.py -q
python -m pytest tests/unit -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit**

```bash
git add app/services/filter_engine.py app/services/filter_rules app/services/market_context_service.py tests/unit/test_filter_rule_modules.py
git commit -m "refactor: split filter engine rule modules"
```

---

## Task 2: Signal Bot Config Validation Service

**Files:**
- Create: `app/services/config_validation.py`
- Modify: `app/repositories/config_repo.py`
- Test: `tests/unit/test_config_validation.py`
- Test: `tests/unit/test_config_repo.py`

- [ ] **Step 1: Write config validation tests**

Create `tests/unit/test_config_validation.py`:

```python
from __future__ import annotations

import pytest

from app.repositories.config_repo import ConfigRepository, _deep_merge
from app.services.config_validation import ConfigValidationError, validate_signal_bot_config


def test_default_signal_bot_config_validates() -> None:
    validated = validate_signal_bot_config(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)

    assert validated["allowed_symbols"] == ["BTCUSDT", "BTCUSD"]
    assert validated["market_context"]["enabled"] is False


def test_rejects_invalid_confidence_threshold_range() -> None:
    config = _deep_merge(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG, {"confidence_thresholds": {"5m": 1.5}})

    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)

    assert "confidence_thresholds.5m" in str(exc.value)


def test_rejects_unknown_top_level_key() -> None:
    config = _deep_merge(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG, {"unexpected": True})

    with pytest.raises(ConfigValidationError) as exc:
        validate_signal_bot_config(config)

    assert "unexpected" in str(exc.value)


def test_accepts_market_context_warn_mode() -> None:
    config = _deep_merge(
        ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG,
        {"market_context": {"enabled": True, "regime_mismatch_mode": "WARN", "snapshot_max_age_minutes": 15}},
    )

    validated = validate_signal_bot_config(config)

    assert validated["market_context"]["regime_mismatch_mode"] == "WARN"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/unit/test_config_validation.py -q
```

Expected: import failure for `app.services.config_validation`.

- [ ] **Step 3: Implement validation service**

Create `app/services/config_validation.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConfigValidationError(ValueError):
    pass


class MarketContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    regime_mismatch_mode: Literal["WARN"] = "WARN"
    snapshot_max_age_minutes: int = Field(default=10, ge=1, le=1440)


class StrategyThresholds(BaseModel):
    model_config = ConfigDict(extra="allow")


class SignalBotConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_symbols: list[str]
    allowed_timeframes: list[str]
    confidence_thresholds: dict[str, float]
    cooldown_minutes: dict[str, int]
    rr_min_base: float = Field(gt=0)
    rr_min_squeeze: float = Field(gt=0)
    duplicate_price_tolerance_pct: float = Field(gt=0, lt=1)
    enable_news_block: bool
    news_block_before_min: int = Field(ge=0)
    news_block_after_min: int = Field(ge=0)
    log_reject_to_admin: bool
    rr_tolerance_pct: float = Field(ge=0, lt=1)
    rr_target_by_type: dict[str, float]
    score_pass_threshold: int = Field(ge=0, le=100)
    strategy_thresholds: dict[str, dict[str, Any]]
    rescoring: dict[str, dict[str, Any]]
    auto_create_open_outcomes: bool = False
    market_context: MarketContextConfig = Field(default_factory=MarketContextConfig)

    @field_validator("allowed_symbols", "allowed_timeframes")
    @classmethod
    def non_empty_string_list(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("must contain at least one non-empty string")
        return value

    @field_validator("confidence_thresholds")
    @classmethod
    def confidence_values_in_range(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("must contain at least one timeframe")
        for key, threshold in value.items():
            if not 0.0 <= float(threshold) <= 1.0:
                raise ValueError(f"confidence_thresholds.{key} must be between 0 and 1")
        return value

    @field_validator("cooldown_minutes")
    @classmethod
    def cooldown_values_positive(cls, value: dict[str, int]) -> dict[str, int]:
        if not value:
            raise ValueError("must contain at least one timeframe")
        for key, minutes in value.items():
            if int(minutes) <= 0:
                raise ValueError(f"cooldown_minutes.{key} must be positive")
        return value


def validate_signal_bot_config(config: dict) -> dict:
    try:
        return SignalBotConfigModel.model_validate(config).model_dump(mode="json")
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigValidationError(details) from exc
```

- [ ] **Step 4: Add default `market_context` to config repository**

Modify `ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG` in `app/repositories/config_repo.py`:

```python
"auto_create_open_outcomes": False,
"market_context": {
    "enabled": False,
    "regime_mismatch_mode": "WARN",
    "snapshot_max_age_minutes": 10,
},
```

- [ ] **Step 5: Validate writes strictly and reads as warning-only**

In `app/repositories/config_repo.py`, import:

```python
from app.services.config_validation import ConfigValidationError, validate_signal_bot_config
```

For read paths, do not raise on invalid legacy config. Use this pattern in both `get_signal_bot_config()` and `get_signal_bot_config_with_version()`:

```python
try:
    validate_signal_bot_config(merged_config)
except ConfigValidationError as exc:
    logger.warning("signal_bot_config_validation_warning", extra={"error": str(exc)})
```

Return the merged config even if validation warns. This preserves webhook continuity when DB config contains manual legacy keys.

For write paths, validation is strict. In `update_config_with_audit()` validate before assignment:

```python
validated_value = validate_signal_bot_config(new_value)
```

Save `validated_value` to `config.config_value` and to the audit row.

- [ ] **Step 6: Run config tests**

Run:

```bash
python -m pytest tests/unit/test_config_validation.py tests/unit/test_config_repo.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Verify legacy read compatibility**

Before closing the task, verify read-path behavior with an invalid legacy config fixture or manual DB patch:

```python
config = ConfigRepository(db_session).get_signal_bot_config()
assert isinstance(config, dict)
```

Expected:

- invalid legacy keys do not crash reads;
- a warning log is emitted;
- write paths still reject the same payload.

- [ ] **Step 8: Commit**

```bash
git add app/repositories/config_repo.py app/services/config_validation.py tests/unit/test_config_validation.py tests/unit/test_config_repo.py
git commit -m "feat: validate signal bot config"
```

---

## Task 3: Calibration Service Boundary

**Files:**
- Modify: `app/services/calibration_report.py`
- Modify: `app/api/analytics_controller.py`
- Test: `tests/unit/test_calibration_report.py`
- Test: `tests/integration/test_calibration_api.py`

- [ ] **Step 1: Add service-level query builder function**

In `app/services/calibration_report.py`, add a pure transform function that keeps existing `build_calibration_report()` unchanged:

```python
def rows_to_calibration_payload(outcome_rows: list, filter_rows_by_signal: dict[str, list[dict]]) -> list[dict]:
    return [
        {
            "timeframe": row.timeframe,
            "signal_type": row.signal_type,
            "r_multiple": float(row.r_multiple) if row.r_multiple is not None else None,
            "is_win": row.is_win,
            "indicator_confidence": float(row.indicator_confidence) if row.indicator_confidence is not None else None,
            "filter_results": filter_rows_by_signal.get(row.id, []),
        }
        for row in outcome_rows
    ]
```

- [ ] **Step 2: Move calibration endpoint assembly into service**

In `app/services/calibration_report.py`, add:

```python
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Signal, SignalFilterResult, SignalOutcome


def build_calibration_report_from_db(db: Session, days: int, min_samples: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    outcome_rows = db.execute(
        select(
            Signal.id,
            Signal.timeframe,
            Signal.signal_type,
            SignalOutcome.r_multiple,
            SignalOutcome.is_win,
            Signal.indicator_confidence,
        )
        .join(Signal, Signal.id == SignalOutcome.signal_row_id)
        .where(Signal.created_at >= since, SignalOutcome.outcome_status == "CLOSED")
    ).all()

    signal_ids = [row.id for row in outcome_rows]
    filter_rows_by_signal: dict[str, list[dict]] = {signal_id: [] for signal_id in signal_ids}
    if signal_ids:
        filter_rows = db.execute(
            select(
                SignalFilterResult.signal_row_id,
                SignalFilterResult.rule_code,
                SignalFilterResult.result,
                SignalFilterResult.severity,
            ).where(SignalFilterResult.signal_row_id.in_(signal_ids))
        ).all()
        for row in filter_rows:
            filter_rows_by_signal.setdefault(row.signal_row_id, []).append(
                {"rule_code": row.rule_code, "result": row.result, "severity": row.severity}
            )

    report = build_calibration_report(rows_to_calibration_payload(outcome_rows, filter_rows_by_signal), min_samples)
    return {"period_days": days, **report}
```

- [ ] **Step 3: Simplify analytics controller**

In `app/api/analytics_controller.py`, change the calibration endpoint to:

```python
from app.services.calibration_report import build_calibration_report_from_db


@router.get("/calibration/report")
def get_calibration_report(
    days: int = Query(90, ge=1, le=365),
    min_samples: int = Query(30, ge=1, le=1000),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    return build_calibration_report_from_db(db, days=days, min_samples=min_samples)
```

Remove now-unused calibration endpoint SQL assembly imports if they become stale.
Remove the old inline SQL/query assembly block from `get_calibration_report()` so the controller body contains only the service call above.

- [ ] **Step 4: Run calibration tests**

Run:

```bash
python -m pytest tests/unit/test_calibration_report.py tests/integration/test_calibration_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/analytics_controller.py app/services/calibration_report.py tests/unit/test_calibration_report.py tests/integration/test_calibration_api.py
git commit -m "refactor: move calibration report assembly to service"
```

---

## Task 4: Replay Service Boundary

**Files:**
- Create: `app/services/replay_service.py`
- Modify: `scripts/replay_payloads.py`
- Test: `tests/unit/test_replay_service.py`
- Test: `tests/unit/test_replay_payloads.py`

- [ ] **Step 1: Add replay service tests**

Create `tests/unit/test_replay_service.py`:

```python
from __future__ import annotations

from app.repositories.config_repo import ConfigRepository
from app.services.replay_service import ReplayService


def _payload() -> dict:
    return {
        "secret": "x",
        "signal": "long",
        "symbol": "BTCUSDT",
        "timeframe": "5",
        "timestamp": "2026-05-02T00:00:00Z",
        "price": 100.0,
        "source": "test",
        "confidence": 0.9,
        "metadata": {"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "signal_type": "LONG_V73"},
    }


def test_replay_payload_returns_ok_record() -> None:
    service = ReplayService(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)

    record = service.replay_payload(_payload(), file_label="sample.json")

    assert record["status"] == "ok"
    assert record["file"] == "sample.json"
    assert record["decision"] in {"PASS_MAIN", "PASS_WARNING", "REJECT"}


def test_replay_payload_returns_error_record_for_invalid_payload() -> None:
    service = ReplayService(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)

    record = service.replay_payload({"bad": "payload"}, file_label="bad.json")

    assert record["status"] == "error"
    assert record["file"] == "bad.json"


def test_compare_payload_reports_decision_fields() -> None:
    service = ReplayService(ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG)
    proposed = {**ConfigRepository._DEFAULT_SIGNAL_BOT_CONFIG, "confidence_thresholds": {"5m": 0.95}}

    record = service.compare_payload(_payload(), proposed_config=proposed, file_label="sample.json")

    assert record["status"] == "ok"
    assert "current_decision" in record
    assert "proposed_decision" in record
    assert "changed_rule_codes" in record
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/unit/test_replay_service.py -q
```

Expected: import failure for `ReplayService`.

- [ ] **Step 3: Implement replay service**

Create `app/services/replay_service.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.schemas import TradingViewWebhookPayload
from app.services.filter_engine import FilterEngine
from app.services.signal_normalizer import SignalNormalizer


class _NoopSignalRepo:
    def find_recent_similar_by_entry_range(self, **kwargs):
        return []

    def find_recent_pass_main_same_side(self, **kwargs):
        return []


class _NoopMarketRepo:
    def find_active_around(self, *args, **kwargs):
        return []


class ReplayService:
    def __init__(self, config: dict):
        self.config = config

    def replay_payload(self, payload_dict: dict[str, Any], file_label: str) -> dict[str, Any]:
        try:
            payload = TradingViewWebhookPayload.model_validate(payload_dict)
            norm = SignalNormalizer.normalize("replay", payload)
            result = FilterEngine(self.config, _NoopSignalRepo(), _NoopMarketRepo()).run(norm)
            return {
                "file": file_label,
                "status": "ok",
                "signal_id": norm["signal_id"],
                "decision": result.final_decision.value,
                "route": result.route.value,
                "server_score": result.server_score,
                "decision_reason": result.decision_reason,
                "rule_codes": [item.rule_code for item in result.filter_results],
            }
        except Exception as exc:
            return {"file": file_label, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    def compare_payload(self, payload_dict: dict[str, Any], proposed_config: dict, file_label: str) -> dict[str, Any]:
        current = self.replay_payload(payload_dict, file_label)
        proposed = ReplayService(proposed_config).replay_payload(payload_dict, file_label)
        if current["status"] != "ok" or proposed["status"] != "ok":
            return {"file": file_label, "status": "error", "current": current, "proposed": proposed}
        current_rules = set(current.get("rule_codes", []))
        proposed_rules = set(proposed.get("rule_codes", []))
        return {
            "file": file_label,
            "status": "ok",
            "signal_id": current["signal_id"],
            "current_decision": current["decision"],
            "proposed_decision": proposed["decision"],
            "current_route": current["route"],
            "proposed_route": proposed["route"],
            "current_server_score": current["server_score"],
            "proposed_server_score": proposed["server_score"],
            "decision_changed": current["decision"] != proposed["decision"],
            "changed_rule_codes": sorted(current_rules.symmetric_difference(proposed_rules)),
        }


def load_json_payloads(input_path: Path) -> list[tuple[Path, dict[str, Any]]]:
    paths = [input_path] if input_path.is_file() else sorted(path for path in input_path.rglob("*.json") if path.is_file())
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
```

- [ ] **Step 4: Update CLI wrapper**

Modify `scripts/replay_payloads.py` to use `ReplayService` for record creation while keeping existing CLI arguments and JSONL output. Preserve output fields `config_db_key`, `dry_run`, and `persisted` by adding them after service returns each record.
Remove the old `_NoopSignalRepo` and `_NoopMarketRepo` classes from the CLI after the service extraction so those test doubles live in one place only.

- [ ] **Step 5: Run replay tests**

Run:

```bash
python -m pytest tests/unit/test_replay_service.py tests/unit/test_replay_payloads.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/replay_service.py scripts/replay_payloads.py tests/unit/test_replay_service.py tests/unit/test_replay_payloads.py
git commit -m "refactor: extract replay service"
```

---

## Task 5: Market Context Repository Tolerance And Index

**Files:**
- Create: `migrations/010_v13_market_context_index.sql`
- Modify: `app/repositories/market_context_repo.py`
- Modify: `app/services/market_context_service.py`
- Modify: `tests/integration/test_ci_migration_fixture.py`
- Test: `tests/unit/test_market_context_service.py`
- Test: `tests/integration/test_market_context_integration.py`

- [ ] **Step 1: Add migration**

Create `migrations/010_v13_market_context_index.sql`:

```sql
-- Migration 010: Market context lookup index for V1.3 at-or-before-close checks.

CREATE INDEX IF NOT EXISTS idx_market_context_symbol_tf_source_bar_time
ON market_context_snapshots(symbol, timeframe, source, bar_time DESC);
```

Update `tests/integration/test_ci_migration_fixture.py` migration list to include:

```python
("010", "010_v13_market_context_index.sql"),
```

- [ ] **Step 2: Update repository lookup**

Modify `app/repositories/market_context_repo.py`:

```python
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import MarketContextSnapshot


class MarketContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_snapshot(
        self,
        symbol: str,
        timeframe: str,
        bar_time,
        source: str | None = None,
        max_age_minutes: int = 10,
    ) -> MarketContextSnapshot | None:
        lower = bar_time - timedelta(minutes=max_age_minutes)
        stmt = (
            select(MarketContextSnapshot)
            .where(MarketContextSnapshot.symbol == symbol)
            .where(MarketContextSnapshot.timeframe == timeframe)
            .where(MarketContextSnapshot.bar_time >= lower)
            .where(MarketContextSnapshot.bar_time <= bar_time)
            .order_by(MarketContextSnapshot.bar_time.desc())
            .limit(1)
        )
        if source is not None:
            stmt = stmt.where(MarketContextSnapshot.source == source)
        return self.db.execute(stmt).scalar_one_or_none()
```

This task uses the agreed semantic: "most recent snapshot at or before candle close within tolerance", not "absolute nearest snapshot".

If production lookup semantics always include `source`, keep the proposed index as-is. If lookups frequently omit `source`, note in the implementation summary whether a second index on `(symbol, timeframe, bar_time DESC)` is needed after `EXPLAIN ANALYZE`.

- [ ] **Step 3: Update service call signature**

Modify `app/services/market_context_service.py` so `compare_regime()` reads `snapshot_max_age_minutes` and passes `source` to the repository when available:

```python
def compare_regime(self, signal: dict, enabled: bool, snapshot_max_age_minutes: int = 10) -> FilterResult | None:
    if not enabled:
        return None
    bar_time = signal.get("bar_time")
    if bar_time is None:
        return None
    snapshot = self.repo.find_snapshot(
        signal["symbol"],
        signal["timeframe"],
        bar_time,
        source=signal.get("source"),
        max_age_minutes=snapshot_max_age_minutes,
    )
    if snapshot is None or snapshot.backend_regime is None:
        return None
    payload_regime = signal.get("regime")
    if payload_regime == snapshot.backend_regime:
        return FilterResult("BACKEND_REGIME_MISMATCH", "market_context", RuleResult.PASS, RuleSeverity.INFO)
    return FilterResult(
        "BACKEND_REGIME_MISMATCH",
        "market_context",
        RuleResult.WARN,
        RuleSeverity.MEDIUM,
        0.0,
        {"payload_regime": payload_regime, "backend_regime": snapshot.backend_regime},
    )
```

Keep existing PASS/WARN behavior unchanged.

- [ ] **Step 4: Add integration tests for at-or-before-close lookup**

Create `tests/integration/test_market_context_integration.py` with tests that insert snapshots around `bar_time`, call `MarketContextRepository.find_snapshot()`, and assert the latest snapshot at or before `bar_time` inside the tolerance window is returned. Also assert that snapshots newer than `bar_time` are ignored even if they fall inside the old symmetric window. Use the existing integration DB fixture patterns from `tests/integration/conftest.py`.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest tests/unit/test_market_context_service.py tests/integration/test_market_context_integration.py tests/integration/test_ci_migration_fixture.py -q
```

Expected: all selected tests pass when integration DB is available; DB tests skip if env is absent.

- [ ] **Step 6: Verify the index is used**

With PostgreSQL integration DB available, run:

```sql
EXPLAIN ANALYZE
SELECT *
FROM market_context_snapshots
WHERE symbol = 'BTCUSDT'
  AND timeframe = '5m'
  AND source = 'test'
  AND bar_time >= NOW() - INTERVAL '10 minutes'
  AND bar_time <= NOW()
ORDER BY bar_time DESC
LIMIT 1;
```

Expected: PostgreSQL uses the `idx_market_context_symbol_tf_source_bar_time` index path rather than a full sequential scan.

- [ ] **Step 7: Commit**

```bash
git add app/repositories/market_context_repo.py app/services/market_context_service.py migrations/010_v13_market_context_index.sql tests/unit/test_market_context_service.py tests/integration/test_market_context_integration.py tests/integration/test_ci_migration_fixture.py
git commit -m "feat: add tolerant market context lookup"
```

---

## Task 6: Market Context Advisory Filter Integration

**Files:**
- Create: `app/services/filter_rules/market_context.py`
- Modify: `app/services/filter_engine.py`
- Modify: `app/services/webhook_ingestion_service.py` only if a dedicated market context repo must be injected.
- Test: `tests/unit/test_filter_engine.py`
- Test: `tests/integration/test_market_context_integration.py`

- [ ] **Step 1: Add filter engine test for advisory mismatch**

In `tests/unit/test_filter_engine.py`, add a repo fake that returns a snapshot with mismatched `backend_regime`, then assert final decision is `PASS_WARNING` and rule code `BACKEND_REGIME_MISMATCH` is present when config enables market context.

Use this assertion shape:

```python
assert result.final_decision.value == "PASS_WARNING"
assert any(item.rule_code == "BACKEND_REGIME_MISMATCH" and item.result.value == "WARN" for item in result.filter_results)
```

- [ ] **Step 2: Create market context rule adapter**

Create `app/services/filter_rules/market_context.py`:

```python
from __future__ import annotations

from app.services.filter_rules.types import FilterResult
from app.services.market_context_service import MarketContextService


def check_market_context(signal: dict, config: dict, market_context_repo, results: list[FilterResult]) -> None:
    market_config = config.get("market_context", {})
    enabled = bool(market_config.get("enabled", False))
    max_age = int(market_config.get("snapshot_max_age_minutes", 10))
    result = MarketContextService(market_context_repo).compare_regime(
        signal,
        enabled=enabled,
        snapshot_max_age_minutes=max_age,
    )
    if result is not None:
        results.append(result)
```

- [ ] **Step 3: Wire adapter into FilterEngine**

In `app/services/filter_engine.py`, accept a fourth optional repo only if needed. Preferred path: reuse `market_event_repo` only for news and add `market_context_repo` defaulting to `None`:

```python
def __init__(self, config: dict, signal_repo: Any, market_event_repo: Any, market_context_repo: Any | None = None):
    self.config = config
    self.signal_repo = signal_repo
    self.market_event_repo = market_event_repo
    self.market_context_repo = market_context_repo
```

Call `check_market_context()` after hard business rules pass and before advisory warnings when `self.market_context_repo is not None`.

- [ ] **Step 4: Inject repository during webhook ingestion**

In `app/services/webhook_ingestion_service.py`, instantiate `MarketContextRepository(db)` and pass it to `FilterEngine`. Keep existing tests compatible by giving `FilterEngine` a default for the new parameter.

- [ ] **Step 5: Run filter and webhook tests**

Run:

```bash
python -m pytest tests/unit/test_filter_engine.py tests/unit/test_market_context_service.py -q
python -m pytest tests/integration/test_webhook_endpoint.py tests/integration/test_market_context_integration.py -q
```

Expected: all selected tests pass when integration DB is available.

- [ ] **Step 6: Commit**

```bash
git add app/services/filter_engine.py app/services/filter_rules/market_context.py app/services/webhook_ingestion_service.py tests/unit/test_filter_engine.py tests/integration/test_market_context_integration.py
git commit -m "feat: add market context advisory filter"
```

---

## Task 7: Calibration Proposal Service And API

**Files:**
- Create: `app/services/calibration_proposals.py`
- Modify: `app/api/analytics_controller.py`
- Modify: `app/domain/schemas.py`
- Test: `tests/unit/test_calibration_proposals.py`
- Test: `tests/integration/test_calibration_proposals_api.py`

- [ ] **Step 1: Write proposal service tests**

Create `tests/unit/test_calibration_proposals.py`:

```python
from __future__ import annotations

from app.services.calibration_proposals import build_calibration_proposals


def test_confidence_threshold_proposal_clamps_step() -> None:
    report = {
        "threshold_suggestions": [
            {
                "config_key": "confidence_thresholds.5m",
                "suggested": 0.9,
                "samples": 80,
                "avg_r": -0.2,
                "confidence": "MEDIUM",
                "reason": "negative avg R",
            }
        ]
    }
    config = {"confidence_thresholds": {"5m": 0.78}}

    proposals = build_calibration_proposals(report, config, current_config_version=3, min_samples=30)

    assert proposals["current_config_version"] == 3
    assert proposals["proposals"][0]["current"] == 0.78
    assert proposals["proposals"][0]["suggested"] == 0.81
    assert proposals["proposals"][0]["direction"] == "TIGHTEN"


def test_no_proposal_when_samples_below_minimum() -> None:
    report = {
        "threshold_suggestions": [
            {"config_key": "confidence_thresholds.5m", "suggested": 0.81, "samples": 10, "avg_r": -0.2, "confidence": "LOW", "reason": "negative avg R"}
        ]
    }
    config = {"confidence_thresholds": {"5m": 0.78}}

    proposals = build_calibration_proposals(report, config, current_config_version=3, min_samples=30)

    assert proposals["proposals"] == []
```

- [ ] **Step 2: Implement proposal service**

Create `app/services/calibration_proposals.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone


def build_calibration_proposals(
    report: dict,
    current_config: dict,
    current_config_version: int,
    min_samples: int,
) -> dict:
    proposals = []
    for item in report.get("threshold_suggestions", []):
        config_key = str(item["config_key"])
        parts = config_key.split(".")
        if len(parts) != 2 or parts[0] != "confidence_thresholds":
            continue
        timeframe = parts[1]
        samples = int(item.get("samples") or 0)
        if samples < min_samples:
            continue
        current = float(current_config.get("confidence_thresholds", {}).get(timeframe))
        raw_suggested = float(item["suggested"])
        max_step = 0.03
        if raw_suggested > current:
            suggested = min(raw_suggested, current + max_step)
            direction = "TIGHTEN"
        elif raw_suggested < current:
            suggested = max(raw_suggested, current - max_step)
            direction = "RELAX"
        else:
            continue
        suggested = round(max(0.0, min(1.0, suggested)), 2)
        proposals.append(
            {
                "id": f"confidence_thresholds.{timeframe}.{direction.lower()}.{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "config_path": config_key,
                "current": current,
                "suggested": suggested,
                "direction": direction,
                "reason": item.get("reason") or "Calibration report suggested a threshold change",
                "sample_health": {
                    "samples": samples,
                    "win_rate": item.get("win_rate", 0.0),
                    "avg_r": item.get("avg_r", 0.0),
                },
                "confidence": "LOW" if samples < min_samples * 2 else item.get("confidence", "MEDIUM"),
                "risk": f"May change signal volume on {timeframe}",
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_config_version": current_config_version,
        "proposals": proposals,
    }
```

Document the contract explicitly: `build_calibration_proposals()` reads the current threshold value from live config, not from any `current` field inside `threshold_suggestions`.

- [ ] **Step 3: Add API endpoint**

In `app/api/analytics_controller.py`, add:

```python
from app.repositories.config_repo import ConfigRepository
from app.services.calibration_proposals import build_calibration_proposals


@router.get("/calibration/proposals")
def get_calibration_proposals(
    days: int = Query(90, ge=1, le=365),
    min_samples: int = Query(30, ge=1, le=1000),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    report = build_calibration_report_from_db(db, days=days, min_samples=min_samples)
    current_config, version = ConfigRepository(db).get_signal_bot_config_with_version()
    proposals = build_calibration_proposals(report, current_config, current_config_version=version, min_samples=min_samples)
    return {"period_days": days, "min_samples": min_samples, **proposals}
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/unit/test_calibration_proposals.py tests/integration/test_calibration_proposals_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/analytics_controller.py app/services/calibration_proposals.py app/domain/schemas.py tests/unit/test_calibration_proposals.py tests/integration/test_calibration_proposals_api.py
git commit -m "feat: add calibration proposal API"
```

---

## Task 8: Config Dry-Run And Rollback

**Files:**
- Modify: `app/api/config_controller.py`
- Modify: `app/repositories/config_repo.py`
- Modify: `app/domain/schemas.py`
- Test: `tests/integration/test_config_api.py`
- Test: `tests/integration/test_config_dry_run_rollback.py`

- [ ] **Step 1: Add dry-run endpoint tests**

Create `tests/integration/test_config_dry_run_rollback.py` using the dashboard auth header from existing config tests. Assert:

```python
resp = client.post(
    "/api/v1/admin/config/signal-bot/dry-run",
    json={"config_value": {"confidence_thresholds": {"5m": 0.81}}, "change_reason": "Raise 5m threshold after calibration review"},
    headers={"Authorization": "Bearer test-dash-token"},
)
assert resp.status_code == 200
body = resp.json()
assert body["changed_paths"] == ["confidence_thresholds.5m"]
```

Also assert the real config version did not change after dry-run.

- [ ] **Step 2: Implement changed-path diff helper**

In `app/repositories/config_repo.py`, add:

```python
def diff_config_paths(old: dict, new: dict, prefix: str = "") -> list[str]:
    paths: list[str] = []
    keys = old.keys() | new.keys()
    for key in sorted(keys):
        path = f"{prefix}.{key}" if prefix else str(key)
        old_value = old.get(key)
        new_value = new.get(key)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            paths.extend(diff_config_paths(old_value, new_value, path))
        elif old_value != new_value:
            paths.append(path)
    return paths
```

- [ ] **Step 3: Add dry-run endpoint**

In `app/api/config_controller.py`, add:

```python
@router.post("/signal-bot/dry-run")
def dry_run_signal_bot_config(
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    change_reason = str(payload.get("change_reason") or "").strip()
    if len(change_reason) < 10:
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_REASON_REQUIRED", "message": "change_reason must be at least 10 characters"})
    config_patch = payload.get("config_value")
    if not isinstance(config_patch, dict):
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_VALIDATION_FAILED", "message": "config_value must be an object"})
    from app.repositories.config_repo import _deep_merge, diff_config_paths
    repo = ConfigRepository(db)
    current_config, version = repo.get_signal_bot_config_with_version()
    merged = _deep_merge(current_config, config_patch)
    from app.services.config_validation import ConfigValidationError, validate_signal_bot_config
    try:
        validated = validate_signal_bot_config(merged)
    except ConfigValidationError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "CONFIG_VALIDATION_FAILED", "message": str(exc)}) from exc
    return {
        "config_key": "signal_bot_config",
        "current_version": version,
        "changed_paths": diff_config_paths(current_config, validated),
        "config_value": validated,
        "warnings": [],
    }
```

- [ ] **Step 4: Add rollback support with audit-log scan**

Use the minimum-change V1.3 approach: reconstruct historical config values by scanning audit logs backward from the current version. Do not add a new migration for version columns in this slice.

Implement this repository method:

```python
def get_config_value_by_version(self, config_key: str, target_version: int) -> dict | None:
    current = self.db.execute(
        select(SystemConfig).where(SystemConfig.config_key == config_key)
    ).scalar_one_or_none()
    if not current:
        return None
    if int(current.version or 1) == target_version:
        return copy.deepcopy(current.config_value)

    logs = self.db.execute(
        select(SystemConfigAuditLog)
        .where(SystemConfigAuditLog.config_key == config_key)
        .order_by(SystemConfigAuditLog.created_at.desc())
    ).scalars().all()

    version = int(current.version or 1)
    for log in logs:
        if version == target_version:
            return copy.deepcopy(log.new_value)
        version -= 1
        if version == target_version:
            return copy.deepcopy(log.old_value)
    return None
```

Then implement the rollback endpoint by:

1. validating `target_version`;
2. loading the historic config with `get_config_value_by_version()`;
3. calling `update_config_with_audit()` with that historic value;
4. returning the new live version and the rollback source version.

Endpoint:

```text
POST /api/v1/admin/config/signal-bot/rollback
```

Request:

```json
{"target_version": 4, "change_reason": "Rollback after replay showed warning route spike"}
```

Response includes new version and target version.

- [ ] **Step 5: Run config integration tests**

Run:

```bash
python -m pytest tests/integration/test_config_api.py tests/integration/test_config_dry_run_rollback.py -q
```

Expected: all selected tests pass when integration DB is available.

- [ ] **Step 6: Verify rollback creates a new live version**

Verify this sequence in integration tests or a local DB session:

1. read current config version;
2. apply a config patch and confirm version increments by 1;
3. roll back to the prior version and confirm the live version increments again;
4. confirm the rolled-back config value matches the historic target version.

Expected: rollback creates a fresh live version; it does not overwrite prior state.

- [ ] **Step 7: Commit**

```bash
git add app/api/config_controller.py app/repositories/config_repo.py app/domain/schemas.py tests/integration/test_config_api.py tests/integration/test_config_dry_run_rollback.py
git commit -m "feat: add config dry-run and rollback"
```

---

## Task 9: Replay Config Compare Mode

**Files:**
- Modify: `app/services/replay_service.py`
- Modify: `scripts/replay_payloads.py`
- Test: `tests/unit/test_replay_service.py`
- Test: `tests/unit/test_replay_payloads.py`

- [ ] **Step 1: Extend CLI parser**

In `scripts/replay_payloads.py`, add arguments:

```python
parser.add_argument("--config-file")
parser.add_argument("--compare-config-file")
parser.add_argument("--database-url")
```

Keep existing arguments unchanged.

- [ ] **Step 2: Add config file loader**

In `scripts/replay_payloads.py`, add:

```python
def _load_config_file(path: str | None, fallback: dict) -> dict:
    if not path:
        return fallback
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

- [ ] **Step 3: Use compare mode when requested**

When `--compare-config-file` is present, call:

```python
record = service.compare_payload(payload_dict, proposed_config=proposed_config, file_label=str(file_path))
```

Otherwise call:

```python
record = service.replay_payload(payload_dict, file_label=str(file_path))
```

- [ ] **Step 4: Add summary output**

In `ReplayService`, add:

```python
def summarize_compare_records(records: list[dict]) -> dict:
    ok_records = [record for record in records if record.get("status") == "ok"]
    return {
        "total": len(records),
        "changed_decisions": sum(1 for record in ok_records if record.get("decision_changed")),
        "main_to_warn": sum(1 for record in ok_records if record.get("current_route") == "MAIN" and record.get("proposed_route") == "WARN"),
        "pass_to_reject": sum(1 for record in ok_records if str(record.get("current_decision", "")).startswith("PASS") and record.get("proposed_decision") == "REJECT"),
        "reject_to_pass": sum(1 for record in ok_records if record.get("current_decision") == "REJECT" and str(record.get("proposed_decision", "")).startswith("PASS")),
    }
```

Print this summary to stdout after JSONL file write in compare mode.

- [ ] **Step 5: Run replay tests**

Run:

```bash
python -m pytest tests/unit/test_replay_service.py tests/unit/test_replay_payloads.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/replay_service.py scripts/replay_payloads.py tests/unit/test_replay_service.py tests/unit/test_replay_payloads.py
git commit -m "feat: add replay config compare mode"
```

---

## Task 10: Dashboard Decision Intelligence Panel

**Files:**
- Modify: `app/templates/dashboard.html`
- Test: `tests/integration/test_dashboard_command_center.py`
- Test: `tests/integration/test_dashboard_auth.py`

- [ ] **Step 1: Add dashboard API fetch**

In `app/templates/dashboard.html`, extend the existing dashboard data loader with a fetch to:

```text
/api/v1/analytics/calibration/proposals?days=90&min_samples=30
```

Use the existing auth token fetch helper pattern.

- [ ] **Step 2: Add panel markup**

Add a section titled `Decision Intelligence` with IDs:

```html
<section class="section">
  <div class="section-header">
    <h2>Decision Intelligence</h2>
  </div>
  <div id="proposal-list" class="subgrid">
    <div class="empty-state">No calibration proposals.</div>
  </div>
</section>
```

Keep existing visual density and avoid nested cards inside cards.

- [ ] **Step 3: Render proposals**

Add JavaScript function:

```javascript
function renderProposals(data) {
  const list = document.getElementById('proposal-list');
  const rows = data.proposals || [];
  if (!rows.length) {
    list.innerHTML = '<div class="empty-state">No calibration proposals.</div>';
    return;
  }
  list.innerHTML = rows.map((item) => `
    <div class="metric-card">
      <span class="label">${escapeHtml(item.config_path)}</span>
      <strong>${escapeHtml(String(item.current))} -> ${escapeHtml(String(item.suggested))}</strong>
      <span class="muted">${escapeHtml(item.direction)} | ${escapeHtml(item.confidence)}</span>
      <span class="muted">${escapeHtml(item.reason)}</span>
    </div>
  `).join('');
}
```

Use an existing `escapeHtml` helper if present; if absent, add one.

- [ ] **Step 4: Run dashboard tests**

Run:

```bash
python -m pytest tests/integration/test_dashboard_auth.py tests/integration/test_dashboard_command_center.py -q
```

Expected: all selected tests pass when integration DB is available.

- [ ] **Step 5: Manual visual QA**

Start the app locally, open `/dashboard`, verify:

- desktop layout has no overlapping text;
- mobile width keeps proposal cards readable;
- no secret/token is printed as visible page text.

- [ ] **Step 6: Commit**

```bash
git add app/templates/dashboard.html tests/integration/test_dashboard_command_center.py
git commit -m "feat: show decision intelligence dashboard"
```

---

## Task 11: Docs, Version, And Release Handoff

**Files:**
- Modify: `docs/API_REFERENCE.md`
- Modify: `docs/DATABASE_SCHEMA.md`
- Modify: `docs/FILTER_RULES.md`
- Modify: `docs/QA_STRATEGY.md`
- Modify: `docs/VERSION_HISTORY.md`
- Modify: `docs/LOCAL_SMOKE_CHECKLIST.md`
- Create: `docs/RELEASE_V13_HANDOFF.md`
- Modify: `app/core/config.py`

- [ ] **Step 1: Update app version**

In `app/core/config.py`, set:

```python
app_version: str = "1.3.0"
```

- [ ] **Step 2: Update API docs**

Document these endpoints in `docs/API_REFERENCE.md`:

```text
GET /api/v1/analytics/calibration/proposals
POST /api/v1/admin/config/signal-bot/dry-run
POST /api/v1/admin/config/signal-bot/rollback
```

Include auth requirement, request body, response body, and failure cases.

- [ ] **Step 3: Update filter docs**

In `docs/FILTER_RULES.md`, document:

```text
BACKEND_REGIME_MISMATCH
Group: market_context
PASS: backend regime matches payload regime
WARN MEDIUM: backend regime conflicts with payload regime
FAIL: not used in V1.3
```

- [ ] **Step 4: Update schema docs**

In `docs/DATABASE_SCHEMA.md`, document migration 010 and index:

```sql
CREATE INDEX IF NOT EXISTS idx_market_context_symbol_tf_source_bar_time
ON market_context_snapshots(symbol, timeframe, source, bar_time DESC);
```

- [ ] **Step 5: Update QA docs**

In `docs/QA_STRATEGY.md` and `docs/LOCAL_SMOKE_CHECKLIST.md`, add V1.3 checks for:

- market context missing/match/mismatch;
- calibration proposal endpoint;
- config dry-run/apply/rollback;
- replay compare CLI;
- dashboard Decision Intelligence panel.

- [ ] **Step 6: Create release handoff**

Create `docs/RELEASE_V13_HANDOFF.md` with sections:

```markdown
# Release 1.3 Handoff

## Branch

- Release branch: `release/1.3`

## Scope Delivered

## New Migrations

## Important New Endpoints

## Dashboard State

## Verification Executed

## Known Release Caveats

## Suggested Next Action
```

Fill each section with the exact implementation result before the final V1.3 merge.

- [ ] **Step 7: Run full verification**

Run:

```bash
python -m pytest tests/unit -q
```

Run when PostgreSQL is available:

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  python -m pytest tests/integration -q
```

Run smoke and migrations:

```bash
bash scripts/smoke_local.sh
python scripts/db/migrate.py apply
python scripts/db/migrate.py status
```

- [ ] **Step 8: Commit**

```bash
git add app/core/config.py docs tests
git commit -m "docs: finalize v1.3 release handoff"
```

---

## Final Verification Before Merge

Run:

```bash
python -m pytest -q
```

Run with PostgreSQL:

```bash
INTEGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/signal_bot' \
  python -m pytest -q
```

Run:

```bash
bash scripts/smoke_local.sh
python scripts/db/migrate.py apply
python scripts/db/migrate.py status
```

Expected:

- all unit tests pass;
- all integration tests pass when DB is available;
- smoke script returns valid, duplicate, invalid JSON, invalid schema success lines;
- migration status lists migrations `001` through `010`.

## Self-Review Notes

- Spec coverage: Phase A through Phase F in `docs/ROADMAP_V1.3.md` map to Tasks 1 through 11.
- Invariants: no task changes persist-before-notify, idempotency, audit-first, or boolean gate routing semantics.
- Calibration remains advisory; config mutation requires admin endpoint and audit.
- Market context starts WARN-only; hard reject remains out of scope.
