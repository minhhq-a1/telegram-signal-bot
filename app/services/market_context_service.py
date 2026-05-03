from __future__ import annotations

from app.services.filter_rules.types import FilterResult
from app.core.enums import RuleResult, RuleSeverity


class MarketContextService:
    def __init__(self, repo):
        self.repo = repo

    def compare_regime(self, signal: dict, enabled: bool) -> FilterResult | None:
        if not enabled:
            return None
        bar_time = signal.get("bar_time")
        if bar_time is None:
            return None
        snapshot = self.repo.find_snapshot(signal["symbol"], signal["timeframe"], bar_time)
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
