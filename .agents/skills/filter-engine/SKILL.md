---
name: filter-engine
description: "Implement, debug, or modify the boolean-gate FilterEngine and V1.1 advisory rules."
---

# Skill: Filter Engine
## Description
Implement, debug, or modify the FilterEngine in `app/services/filter_engine.py`.
Trigger khi user đề cập: filter engine, filter rules, boolean gate, PASS_MAIN, PASS_WARNING, REJECT, rule logic, V1.1 rules.

## Instructions

Đọc `docs/FILTER_RULES.md`, `docs/CHANGELOG_V1.1.md`, và `tests/unit/test_filter_engine.py` trước khi viết code.

### Thiết kế cốt lõi

FilterEngine là **boolean gate**, KHÔNG phải scoring system:

```python
def _decide(results) -> tuple[DecisionType, TelegramRoute]:
    if any(r.result == RuleResult.FAIL for r in results):
        return DecisionType.REJECT, TelegramRoute.NONE

    significant_warns = [
        r for r in results
        if r.result == RuleResult.WARN
        and r.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH, RuleSeverity.CRITICAL)
    ]
    if significant_warns:
        return DecisionType.PASS_WARNING, TelegramRoute.WARN

    return DecisionType.PASS_MAIN, TelegramRoute.MAIN
```

### Thứ tự phases

```
Phase 1: Hard validation
  SYMBOL_ALLOWED → TIMEFRAME_ALLOWED → CONFIDENCE_RANGE → PRICE_VALID
  Short-circuit nếu bất kỳ FAIL

Phase 2: Trade math
  DIRECTION_SANITY_VALID → MIN_RR_REQUIRED
  Short-circuit nếu bất kỳ FAIL

Phase 3a: hard business rules — FAIL → REJECT
  MIN_CONFIDENCE_BY_TF, REGIME_HARD_BLOCK, DUPLICATE_SUPPRESSION, NEWS_BLOCK
  Short-circuit nếu bất kỳ FAIL

Phase 3b: advisory rules — WARN only, không reject
  VOLATILITY_WARNING, COOLDOWN_ACTIVE, LOW_VOLUME_WARNING

Phase 3c: V1.1 quality/advisory rules — WARN MEDIUM → PASS_WARNING
  SQ_RSI_FLOOR, SQ_KC_POSITION_FLOOR,
  S_BASE_RSI_FLOOR, S_BASE_STOCH_FLOOR,
  L_BASE_RSI_FLOOR, L_BASE_STOCH_FLOOR,
  RR_PROFILE_MATCH, BACKEND_SCORE_THRESHOLD

Phase 4: _build_result() → tính server_score để log, gọi _decide() để route
```

### server_score

```python
# Tính để lưu DB analytics — KHÔNG dùng để route
score = signal["indicator_confidence"] + sum(r.score_delta for r in results)
score = max(0.0, min(1.0, score))
```

`BACKEND_SCORE_THRESHOLD` trong V1.1 chỉ là advisory WARN/pilot theo docs hiện tại; không được biến lại thành score-threshold routing.

### Config keys hiện tại

```python
config = {
    "allowed_symbols": ["BTCUSDT", "BTCUSD"],
    "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
    "confidence_thresholds": {
        "1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76,
        "15m": 0.74, "30m": 0.72, "1h": 0.70,
    },
    "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90},
    "rr_min_base": 1.5,
    "rr_min_squeeze": 2.0,
    "duplicate_price_tolerance_pct": 0.002,
    "enable_news_block": True,
    "news_block_before_min": 15,
    "news_block_after_min": 30,
    "log_reject_to_admin": True,
}
# KHÔNG có main_score_threshold / warning_score_threshold
```

### Market/news block

`MarketEventRepository.find_active_around()` dùng model hiện tại:

```python
MarketEvent.impact == "HIGH"
MarketEvent.start_time <= ts + before_min
MarketEvent.end_time >= ts - after_min
```

Không dùng `is_active` hoặc `impact_level` trừ khi schema được migrate rõ ràng.

### Error handling

- `filter_engine.run()` không raise exception cho rule failures; luôn trả `FilterExecutionResult`.
- Nếu thiếu optional fields cho advisory rules, prefer PASS/skip theo docs thay vì crash.
- Hard validation/trade math FAIL phải tạo filter result để audit.

### Verify sau khi implement

```bash
rtk python -m pytest tests/unit/test_filter_engine.py -v
rtk python -m pytest tests/integration/test_v11_pipeline.py -v
```

Key expectations:
- FAIL present → `REJECT` / `NONE`
- WARN MEDIUM+ present without FAIL → `PASS_WARNING` / `WARN`
- WARN LOW only → `PASS_MAIN` / `MAIN`
- server_score changes do not decide route
- V1.1 quality floors produce WARN/PASS_WARNING, not hard reject
