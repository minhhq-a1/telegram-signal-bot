from __future__ import annotations
import dataclasses
from typing import Any
from app.core.enums import RuleResult, RuleSeverity, DecisionType, TelegramRoute
from app.services.filter_rules.types import FilterResult, FilterExecutionResult, has_fail
from app.services.filter_rules.routing import decide, build_decision_reason
from app.services.filter_rules import validation, trade_math, business, advisory, market_context


class FilterEngine:
    """
    V1.3 orchestrator: delegates rule execution to focused modules.
    Preserves exact phase order and public API from V1.0-V1.2.
    """
    def __init__(self, config: dict, signal_repo: Any, market_event_repo: Any, market_context_repo: Any = None):
        self.config = config
        self.signal_repo = signal_repo
        self.market_event_repo = market_event_repo
        self.market_context_repo = market_context_repo

    def run(self, signal: dict) -> FilterExecutionResult:
        results: list[FilterResult] = []

        # Phase 1: Hard validation
        validation.check_symbol(signal, self.config, results)
        validation.check_timeframe(signal, self.config, results)
        validation.check_confidence_range(signal, self.config, results)
        validation.check_price_valid(signal, self.config, results)

        if has_fail(results):
            return self._build_result(results, signal, "Hard validation failed")

        # Phase 2: Trade math
        trade_math.check_direction_sanity(signal, self.config, results)
        trade_math.check_min_rr(signal, self.config, results)

        if has_fail(results):
            return self._build_result(results, signal, "Trade math failed")

        # Phase 2.5: Strategy-specific validation (V1.1)
        from app.services.strategy_validator import validate_strategy
        results.extend(validate_strategy(signal, self.config))

        if has_fail(results):
            return self._build_result(results, signal, "Strategy validation failed")

        # Phase 3a: Hard business rules
        business.check_min_confidence_by_tf(signal, self.config, results)
        business.check_duplicate(signal, self.config, self.signal_repo, results)
        business.check_news_block(signal, self.config, self.market_event_repo, results)
        business.check_regime_hard_block(signal, self.config, results)

        if has_fail(results):
            return self._build_result(results, signal, "Business rule failed")

        # Phase 3b: Advisory warnings
        if self.market_context_repo is not None:
            market_context.check_market_context(signal, self.config, self.market_context_repo, results)
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

        decision, route = decide(results)
        decision_reason = build_decision_reason(reason, results, decision)

        return FilterExecutionResult(
            filter_results=results,
            server_score=round(score, 4),
            final_decision=decision,
            decision_reason=decision_reason,
            route=route,
        )
