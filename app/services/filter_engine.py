from __future__ import annotations
import dataclasses
from typing import Optional, Any
from datetime import datetime, timezone
from app.core.enums import RuleResult, RuleSeverity, DecisionType, TelegramRoute

@dataclasses.dataclass
class FilterResult:
    rule_code: str
    rule_group: str
    result: RuleResult
    severity: RuleSeverity
    score_delta: float = 0.0
    details: Optional[dict] = None

    def to_dict(self):
        return {
            "rule_code": self.rule_code,
            "rule_group": self.rule_group,
            "result": self.result.value,
            "severity": self.severity.value,
            "score_delta": self.score_delta,
            "details": self.details
        }

@dataclasses.dataclass
class FilterExecutionResult:
    filter_results: list[FilterResult]
    server_score: float
    final_decision: DecisionType
    decision_reason: str
    route: TelegramRoute


class FilterEngine:
    def __init__(self, config: dict, signal_repo: Any, market_event_repo: Any):
        self.config = config
        self.signal_repo = signal_repo
        self.market_event_repo = market_event_repo

    def run(self, signal: dict) -> FilterExecutionResult:
        results: list[FilterResult] = []

        # Phase 1: Hard validation
        self._check_symbol(signal, results)
        self._check_timeframe(signal, results)
        self._check_confidence_range(signal, results)
        self._check_price_valid(signal, results)
        
        if self._has_fail(results):
            return self._build_result(results, signal, "Hard validation failed")

        # Phase 2: Trade math
        self._check_direction_sanity(signal, results)
        self._check_min_rr(signal, results)
        
        if self._has_fail(results):
            return self._build_result(results, signal, "Trade math failed")

        # Phase 3a: Hard business rules
        self._check_min_confidence_by_tf(signal, results)
        self._check_duplicate(signal, results)
        self._check_news_block(signal, results)
        self._check_regime_hard_block(signal, results)
        
        if self._has_fail(results):
            return self._build_result(results, signal, "Business rule failed")

        # Phase 3b: Advisory warnings (không reject, chỉ affect routing)
        self._check_volatility(signal, results)
        self._check_cooldown(signal, results)
        self._check_low_volume(signal, results)

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

    # ---------------------------------------------------------
    # Rule implementations
    # ---------------------------------------------------------

    def _check_symbol(self, signal: dict, results: list[FilterResult]):
        allowed = self.config.get("allowed_symbols", ["BTCUSDT", "BTCUSD"])
        if signal["symbol"] not in allowed:
            results.append(FilterResult("SYMBOL_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL, 0.0, {"allowed": allowed}))
        else:
            results.append(FilterResult("SYMBOL_ALLOWED", "validation", RuleResult.PASS, RuleSeverity.INFO))

    def _check_timeframe(self, signal: dict, results: list[FilterResult]):
        allowed = self.config.get("allowed_timeframes", ["1m", "3m", "5m", "12m", "15m", "30m", "1h"])
        if signal["timeframe"] not in allowed:
            results.append(FilterResult("TIMEFRAME_ALLOWED", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL, 0.0, {"allowed": allowed}))
        else:
            results.append(FilterResult("TIMEFRAME_ALLOWED", "validation", RuleResult.PASS, RuleSeverity.INFO))

    def _check_confidence_range(self, signal: dict, results: list[FilterResult]):
        conf = signal.get("indicator_confidence", -1)
        if 0.0 <= conf <= 1.0:
            results.append(FilterResult("CONFIDENCE_RANGE_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO))
        else:
            results.append(FilterResult("CONFIDENCE_RANGE_VALID", "validation", RuleResult.FAIL, RuleSeverity.HIGH, 0.0, {"confidence": conf}))

    def _check_price_valid(self, signal: dict, results: list[FilterResult]):
        price = signal.get("price", 0)
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss") or 0
        tp = signal.get("take_profit") or 0
        if price > 0 and entry > 0 and sl > 0 and tp > 0:
            results.append(FilterResult("PRICE_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO))
        else:
            results.append(FilterResult("PRICE_VALID", "validation", RuleResult.FAIL, RuleSeverity.HIGH))

    def _check_direction_sanity(self, signal: dict, results: list[FilterResult]):
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", 0)
        side = signal.get("side")

        is_valid = False
        if side == "LONG":
            if sl < entry and entry < tp:
                is_valid = True
        elif side == "SHORT":
            if tp < entry and entry < sl:
                is_valid = True

        if is_valid:
            results.append(FilterResult("DIRECTION_SANITY_VALID", "validation", RuleResult.PASS, RuleSeverity.INFO))
        else:
            results.append(FilterResult("DIRECTION_SANITY_VALID", "validation", RuleResult.FAIL, RuleSeverity.CRITICAL))

    def _check_min_rr(self, signal: dict, results: list[FilterResult]):
        rr = signal.get("risk_reward")
        if rr is None or rr <= 0:
             results.append(FilterResult("MIN_RR_REQUIRED", "trading", RuleResult.FAIL, RuleSeverity.HIGH, 0.0, {"rr": rr}))
             return

        signal_type = signal.get("signal_type")
        if signal_type == "SHORT_SQUEEZE":
             min_rr = self.config.get("rr_min_squeeze", 2.0)
        else:
             min_rr = self.config.get("rr_min_base", 1.5)

        if rr >= min_rr:
             results.append(FilterResult("MIN_RR_REQUIRED", "trading", RuleResult.PASS, RuleSeverity.INFO))
        else:
             results.append(FilterResult("MIN_RR_REQUIRED", "trading", RuleResult.FAIL, RuleSeverity.HIGH, 0.0, {"rr": rr, "min_required": min_rr}))

    def _check_min_confidence_by_tf(self, signal: dict, results: list[FilterResult]):
        tf = signal.get("timeframe")
        conf = signal.get("indicator_confidence", 0)
        thresholds = self.config.get("confidence_thresholds", {
            "1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70
        })
        threshold = thresholds.get(tf, 0.85)

        if conf >= threshold:
             results.append(FilterResult("MIN_CONFIDENCE_BY_TF", "trading", RuleResult.PASS, RuleSeverity.INFO))
        else:
             results.append(FilterResult("MIN_CONFIDENCE_BY_TF", "trading", RuleResult.FAIL, RuleSeverity.HIGH, 0.0, {"confidence": conf, "threshold": threshold}))

    def _check_regime_hard_block(self, signal: dict, results: list[FilterResult]):
        side = signal.get("side")
        regime = signal.get("regime")
        
        if side == "LONG" and regime == "STRONG_TREND_DOWN":
             results.append(FilterResult("REGIME_HARD_BLOCK", "trading", RuleResult.FAIL, RuleSeverity.HIGH))
        elif side == "SHORT" and regime == "STRONG_TREND_UP":
             results.append(FilterResult("REGIME_HARD_BLOCK", "trading", RuleResult.FAIL, RuleSeverity.HIGH))
        else:
             results.append(FilterResult("REGIME_HARD_BLOCK", "trading", RuleResult.PASS, RuleSeverity.INFO))

    def _check_duplicate(self, signal: dict, results: list[FilterResult]):
        tf = signal.get("timeframe")
        cooldowns = self.config.get("cooldown_minutes", {
            "1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90
        })
        minutes = cooldowns.get(tf, 10)
        tolerance = self.config.get("duplicate_price_tolerance_pct", 0.002)

        candidates = self.signal_repo.find_recent_similar(
            symbol=signal["symbol"],
            timeframe=tf,
            side=signal["side"],
            signal_type=signal.get("signal_type"),
            since_minutes=minutes,
            exclude_signal_id=signal.get("signal_id"),
        )
        
        entry = signal.get("entry_price", 0)
        is_duplicate = False
        
        for cand in candidates:
             if cand.entry_price > 0 and abs(entry - float(cand.entry_price)) / float(cand.entry_price) < tolerance:
                 is_duplicate = True
                 break

        if is_duplicate:
             results.append(FilterResult("DUPLICATE_SUPPRESSION", "trading", RuleResult.FAIL, RuleSeverity.HIGH))
        else:
             results.append(FilterResult("DUPLICATE_SUPPRESSION", "trading", RuleResult.PASS, RuleSeverity.INFO))

    def _check_news_block(self, signal: dict, results: list[FilterResult]):
        if not self.config.get("enable_news_block", True):
            return
             
        db_time = datetime.now(timezone.utc)
        if signal.get("payload_timestamp"):
            db_time = signal["payload_timestamp"]
             
        before_min = self.config.get("news_block_before_min", 15)
        after_min = self.config.get("news_block_after_min", 30)
        
        events = self.market_event_repo.find_active_around(db_time, before_min, after_min)
        if events:
             results.append(FilterResult("NEWS_BLOCK", "trading", RuleResult.FAIL, RuleSeverity.HIGH, 0.0, {"active_events": len(events)}))
        else:
             results.append(FilterResult("NEWS_BLOCK", "trading", RuleResult.PASS, RuleSeverity.INFO))

    def _check_volatility(self, signal: dict, results: list[FilterResult]):
        vol = signal.get("vol_regime")
        if vol == "RANGING_HIGH_VOL":
             results.append(FilterResult("VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, -0.08))
        elif vol == "SQUEEZE_BUILDING":
             results.append(FilterResult("VOLATILITY_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW, -0.03))
        elif vol == "TRENDING_HIGH_VOL":
             results.append(FilterResult("VOLATILITY_WARNING", "trading", RuleResult.PASS, RuleSeverity.INFO, 0.03))
        else:
             results.append(FilterResult("VOLATILITY_WARNING", "trading", RuleResult.PASS, RuleSeverity.INFO))

    def _check_low_volume(self, signal: dict, results: list[FilterResult]):
        vr = signal.get("vol_ratio")
        if vr is None or vr >= 1.0:
             results.append(FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.PASS, RuleSeverity.INFO))
        elif vr < 0.8:
             results.append(FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, -0.05))
        else:  # 0.8 <= vr < 1.0
             results.append(FilterResult("LOW_VOLUME_WARNING", "trading", RuleResult.WARN, RuleSeverity.LOW))

    def _check_cooldown(self, signal: dict, results: list[FilterResult]):
        """
        Check cooldown: chỉ warning nếu có prior PASS_MAIN signal cùng symbol+tf+side
        trong cooldown window.
        """
        tf = signal.get("timeframe")
        cooldowns = self.config.get("cooldown_minutes", {
            "1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90
        })
        minutes = cooldowns.get(tf, 10)
        
        cands = self.signal_repo.find_recent_pass_main_same_side(
            symbol=signal["symbol"],
            timeframe=tf,
            side=signal["side"],
            since_minutes=minutes,
            exclude_signal_id=signal.get("signal_id"),
        )
        
        if len(cands) > 0:
             results.append(FilterResult("COOLDOWN_ACTIVE", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, -0.10, {"count": len(cands)}))
        else:
             results.append(FilterResult("COOLDOWN_ACTIVE", "trading", RuleResult.PASS, RuleSeverity.INFO))
