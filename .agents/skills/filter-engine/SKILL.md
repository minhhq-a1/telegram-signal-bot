# Skill: Filter Engine
## Description
Implement, debug, or modify the FilterEngine in `app/services/filter_engine.py`.
Trigger khi user đề cập: filter engine, filter rules, boolean gate, PASS_MAIN, PASS_WARNING, REJECT, rule logic.

## Instructions

Đọc `docs/FILTER_RULES.md` trong project trước khi viết bất kỳ code nào.

### Thiết kế cốt lõi

FilterEngine là **boolean gate**, KHÔNG phải scoring system:

```python
def _decide(results) -> tuple[DecisionType, TelegramRoute]:
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
```

### Thứ tự phases (bắt buộc)

```
Phase 1: SYMBOL_ALLOWED → TIMEFRAME_ALLOWED → CONFIDENCE_RANGE → PRICE_VALID
         Short-circuit nếu bất kỳ FAIL

Phase 2: DIRECTION_SANITY_VALID → MIN_RR_REQUIRED
         Short-circuit nếu bất kỳ FAIL

Phase 3a (hard rules — FAIL → REJECT):
  MIN_CONFIDENCE_BY_TF, REGIME_HARD_BLOCK, DUPLICATE_SUPPRESSION, NEWS_BLOCK
  Short-circuit nếu bất kỳ FAIL

Phase 3b (advisory — WARN only, không reject):
  VOLATILITY_WARNING, COOLDOWN_ACTIVE, LOW_VOLUME_WARNING

Phase 4: _build_result() → tính server_score để log, gọi _decide() để route
```

### server_score

```python
# Tính để lưu DB analytics — KHÔNG dùng để route
score = signal["indicator_confidence"] + sum(r.score_delta for r in results)
score = max(0.0, min(1.0, score))
```

### Config keys cần thiết

```python
config = {
    "allowed_symbols": [...],
    "allowed_timeframes": [...],
    "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74},
    "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25},
    "rr_min_base": 1.5,
    "rr_min_squeeze": 2.0,
    "duplicate_price_tolerance_pct": 0.2,
    "news_block_before_min": 15,
    "news_block_after_min": 30,
}
# KHÔNG có main_score_threshold / warning_score_threshold
```

### Verify sau khi implement

```bash
python -m pytest tests/unit/test_filter_engine.py -v
# Phải pass: test_pass_main, test_reject_low_confidence,
# test_ranging_high_vol_routes_to_warning_not_reject,
# test_cooldown_always_routes_to_warning, test_reject_low_rr
```
