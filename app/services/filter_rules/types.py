"""
Shared types for filter rule modules.
"""
from __future__ import annotations
import dataclasses
from app.core.enums import RuleResult, RuleSeverity


@dataclasses.dataclass
class FilterResult:
    rule_code: str
    rule_group: str
    result: RuleResult
    severity: RuleSeverity
    score_delta: float = 0.0
    details: dict | None = None

    def to_dict(self):
        return {
            "rule_code": self.rule_code,
            "rule_group": self.rule_group,
            "result": self.result.value,
            "severity": self.severity.value,
            "score_delta": self.score_delta,
            "details": self.details
        }
