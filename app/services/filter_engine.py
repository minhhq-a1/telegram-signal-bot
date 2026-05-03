from __future__ import annotations
import dataclasses
from typing import Any
from app.core.enums import RuleResult, RuleSeverity, DecisionType, TelegramRoute
from app.services.filter_rules.types import FilterResult
from app.services.filter_rules import routing, validation, trade_math, business, advisory


@dataclasses.dataclass
class FilterExecutionResult:
    filter_results: list[FilterResult]
    server_score: float
    final_decision: DecisionType
    decision_reason: str
    route: TelegramRoute


class FilterEngine:
    """
    V1.3 orchestrator: delegates rule execution to focused modules.
    Preserves exact phase order and public API from V1.0-V1.2.
    """
    def __init__(self, config: dict, signal_repo: Any, market_event_repo: Any):
        self.config = config
        self.signal_repo = signal_repo
        self.market_event_repo = market_event_repo

    def run(self, signal: dict) -> FilterExecutionResult:
        results: list[FilterResult] = []

        # Phase 1: Hard validation
        routing.check_symbol(signal, self.config, results)
        routing.check_timeframe(signal, self.config, results)
        validation.check_confidence_range(signal, self.config, results)
        validation.check_price_valid(signal, self.config, results)

        if self._has_fail(results):
            return self._build_result(results, signal, "Hard validation failed")

        # Phase 2: Trade math
        trade_math.check_direction_sanity(signal, self.config, results)
        trade_math.check_min_rr(signal, self.config, results)

        if self._has_fail(results):
            return self._build_result(results, signal, "Trade math failed")

        # Phase 2.5: Strategy-specific validation (V1.1)
        from app.services.strategy_validator import validate_strategy
        results.extend(validate_strategy(signal, self.config))

        if self._has_fail(results):
            return self._build_result(results, signal, "Strategy validation failed")

        # Phase 3a: Hard business rules
        business.check_min_confidence_by_tf(signal, self.config, results)
        business.check_duplicate(signal, self.config, self.signal_repo, results)
        business.check_news_block(signal, self.config, self.market_event_repo, results)
        business.check_regime_hard_block(signal, self.config, results)

        if self._has_fail(results):
            return self._build_result(results, signal, "Business rule failed")

        # Phase 3b: Advisory warnings
        advisory.check_volatility(signal, self.config, results)
        advisory.check_cooldown(signal, self.config, self.signal_repo, results)
        advisory.check_low_volume(signal, self.config, results)

        # Phase 3c: RR profile match (V1.1)
        advisory.check_rr_profile_match(signal, self.config, results)

        # Phase 3d: Backend rescoring + threshold (V1.1)
        advisory.check_backend_score(signal, self.config, results)

        # Phase 4: Route
        return self._build_result(results, signal, "Filters passed")

    def _build_result(self, results: list[FilterResult], signal: dict, reason: str) -> FilterExecutionResult:
        score = signal.get("indicator_confidence", 0.0)
        for r in results:
            score += r.score_delta
        score = max(0.0, min(1.0, score))

        decision, route = self._decide(results)
        decision_reason = self._build_decision_reason(reason, results, decision)

        return FilterExecutionResult(
            filter_results=results,
            server_score=round(score, 4),
            final_decision=decision,
            decision_reason=decision_reason,
            route=route,
        )

    def _decide(self, results: list[FilterResult]) -> tuple[DecisionType, TelegramRoute]:
        if any(r.result == RuleResult.FAIL for r in results):
            return DecisionType.REJECT, TelegramRoute.NONE

        significant_warns = [
            r for r in results
            if r.result == RuleResult.WARN
            and r.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
        ]
        if significant_warns:
            return DecisionType.PASS_WARNING, TelegramRoute.WARN

        return DecisionType.PASS_MAIN, TelegramRoute.MAIN

    def _has_fail(self, results: list[FilterResult]) -> bool:
        return any(r.result == RuleResult.FAIL for r in results)

    def _build_decision_reason(
        self,
        phase_reason: str,
        results: list[FilterResult],
        decision: DecisionType,
    ) -> str:
        fail_codes = [r.rule_code for r in results if r.result == RuleResult.FAIL]
        medium_plus_warn_codes = [
            r.rule_code
            for r in results
            if r.result == RuleResult.WARN and r.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
        ]
        low_warn_codes = [
            r.rule_code
            for r in results
            if r.result == RuleResult.WARN and r.severity == RuleSeverity.LOW
        ]

        if decision == DecisionType.REJECT:
            return f"{phase_reason}: {', '.join(fail_codes)}"

        if decision == DecisionType.PASS_WARNING:
            return f"Warnings triggered: {', '.join(medium_plus_warn_codes)}"

        if low_warn_codes:
            return f"Passed main route with advisory warnings: {', '.join(low_warn_codes)}"

        return "Passed all filters"
