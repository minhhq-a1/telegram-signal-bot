# V1.1 Implementation Plan — Telegram Signal Bot

**Review status:** Đã tích hợp feedback từ `docs/superpowers/plans/2026-04-24-v1.1-plan-review-feedback.md`
**Plan status:** Ready for DEV assignment after direct review fixes on 2026-04-25
**Execution approach:** Task-by-task, mỗi task có test-first workflow

---

## Sổ tay cho DEV

### Các lỗi/cập nhật đã phát hiện trong plan gốc (Opus 4.7)

Trước khi bắt đầu, DEV cần biết các lỗi sau trong plan gốc đã được sửa trong bản này:

| # | Vấn đề | Xem chi tiết |
|---|---|---|
| 1 | `SignalNormalizer.normalize()` nhận **(webhook_event_id, payload)** — 2 tham số, không phải 1 | `app/services/signal_normalizer.py:6` |
| 2 | `DecisionRepository` có method `find_by_signal_row_id()`, KHÔNG có `find_for_signal()` | `app/repositories/decision_repo.py:39` |
| 3 | `signal.squeeze_fired` / `squeeze_on` trong ORM model là `Boolean`, nhưng payload Pine gửi `int (0/1)` | `app/domain/models.py:55-56` |
| 4 | `mom_direction` từ Pine hiện chưa đi qua schema/normalizer/persistence | Bản plan này thêm bước plumbing trước khi strategy validator chạy |
| 5 | `docs/FILTER_RULES.md:459` có typo `duplicate_price_tolerance_pct: 0.2` — phải là `0.002` | Bug typo, giá trị đúng trong migration/DB |
| 6 | Plan gốc dùng `db.query()` trong reverify endpoint và analytics — phải dùng `select()` | SQLAlchemy 2.0 rule |
| 7 | Plan gốc dùng `@router.post("/signals/...")` không có prefix — phải là `@router.post("/api/v1/signals/...")` | Route convention |

### Scope Policy (đã xác nhận)

- `BACKEND_SCORE_THRESHOLD` = **WARN MEDIUM** trong pilot 2 tuần (KHÔNG FAIL) → giữ boolean-gate routing
- RR target-band: **±10%** quanh target của từng signal_type
- `MIN_RR_REQUIRED` giữ nguyên là lower-bound check; thêm rule `RR_PROFILE_MATCH` cho target-band
- `RR_PROFILE_MATCH` trong pilot: upper-bound mismatch = **WARN MEDIUM** (KHÔNG FAIL)
- KHÔNG làm: SOFT_PASS, user profile, position-state risk gate, Redis, cooldown-as-reject
- KHÔNG breaking change: tất cả rule hiện có giữ nguyên

---

## Decision Matrix mới (pilot mode)

| Rule | Severity | Result | Action |
|---|---|---|---|
| `SQ_NO_FIRED` | HIGH | FAIL | REJECT |
| `SQ_BAD_MOM_DIRECTION` | HIGH | FAIL | REJECT |
| `SQ_BAD_VOL_REGIME` | HIGH | FAIL | REJECT |
| `SQ_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `SQ_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING (WARN channel) |
| `SQ_KC_POSITION_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `S_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `S_BASE_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `S_BASE_STOCH_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `L_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `L_BASE_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `L_BASE_STOCH_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `RR_PROFILE_MATCH` (upper-bound) | MEDIUM | WARN | → PASS_WARNING (pilot) |
| `BACKEND_SCORE_THRESHOLD` | MEDIUM | WARN | → PASS_WARNING (pilot) |
| `MIN_RR_REQUIRED` (lower-bound) | HIGH | FAIL | REJECT (unchanged) |

---

## Task 0: Setup — Config defaults + Migration 002

**Mục tiêu:** Thêm V1.1 config keys vào code defaults + seed DB qua migration

### Step 0.1: Mở rộng `_DEFAULT_SIGNAL_BOT_CONFIG` trong `config_repo.py`

Thêm sau dòng 53 (trước `}` đóng của `_DEFAULT_SIGNAL_BOT_CONFIG`):

```python
# --- V1.1 config defaults ---
"rr_tolerance_pct": 0.10,
"rr_target_by_type": {
    "SHORT_SQUEEZE": 2.5,
    "SHORT_V73": 1.67,
    "LONG_V73": 1.67,
},
"score_pass_threshold": 75,
"strategy_thresholds": {
    "SHORT_SQUEEZE": {
        "rsi_min": 35,
        "rsi_slope_max": -2,
        "kc_position_max": 0.55,
        "atr_pct_min": 0.20,
    },
    "SHORT_V73": {
        "rsi_min": 60,
        "stoch_k_min": 70,
    },
    "LONG_V73": {
        "rsi_max": 35,
        "stoch_k_max": 20,
    },
},
"rescoring": {
    "SHORT_SQUEEZE": {
        "base": 70,
        "bonuses": {
            "vol_regime_breakout_imminent": 8,
            "regime_weak_trend_down": 6,
            "regime_strong_trend_down": 8,
            "mom_direction_neg1": 5,
            "squeeze_bars_ge_4": 3,
            "squeeze_bars_ge_6": 5,
            "rsi_ge_40": 4,
            "rsi_slope_le_neg4": 4,
            "atr_percentile_ge_70": 3,
            "kc_position_le_040": 3,
            "confidence_ge_090": 3,
        },
        "penalties": {
            "regime_strong_trend_up": -15,
            "regime_weak_trend_up": -8,
            "rsi_lt_35": -8,
            "atr_pct_lt_020": -8,
            "atr_pct_gt_150": -5,
        },
    },
    "SHORT_V73": {
        "base": 72,
        "bonuses": {
            "rsi_ge_70": 5,
            "stoch_ge_85": 5,
            "rsi_slope_le_neg4": 4,
            "regime_trend_down": 6,
            "confidence_ge_090": 3,
        },
        "penalties": {
            "regime_strong_trend_up": -15,
            "vol_ranging_high": -6,
            "atr_pct_lt_020": -6,
        },
    },
    "LONG_V73": {
        "base": 72,
        "bonuses": {
            "rsi_le_25": 5,
            "stoch_le_10": 5,
            "rsi_slope_ge_2": 4,
            "regime_trend_up": 6,
            "confidence_ge_090": 3,
        },
        "penalties": {
            "regime_strong_trend_down": -15,
            "vol_ranging_high": -6,
            "atr_pct_lt_020": -6,
        },
    },
},
```

**Lưu ý:** `score_pass_threshold: 75` là threshold rescoring (0-100 scale), KHÔNG phải `server_score` (0-1 scale).

### Step 0.2: Thêm plumbing cho `mom_direction`

`SHORT_SQUEEZE` hard rule dùng `mom_direction`, nhưng code hiện tại chưa khai báo field này trong `SignalMetadata`, chưa normalize, và chưa persist vào bảng `signals`. Nếu bỏ qua bước này, payload Pine có `"mom_direction": -1` vẫn có thể bị Pydantic bỏ qua, làm `SQ_BAD_MOM_DIRECTION` fail sai cho mọi `SHORT_SQUEEZE`.

Files cần sửa:
- `app/domain/schemas.py`
- `app/services/signal_normalizer.py`
- `app/domain/models.py`
- `app/repositories/signal_repo.py`
- `migrations/003_v11_upgrade.sql`
- tests liên quan đến normalizer / webhook payload

Thêm vào `SignalMetadata`:

```python
mom_direction: int | None = None
```

Thêm vào output của `SignalNormalizer.normalize()`:

```python
"mom_direction": payload.metadata.mom_direction if payload.metadata else None,
```

Thêm column ORM trong `Signal`:

```python
mom_direction: Mapped[int | None] = mapped_column(nullable=True)
```

Thêm mapping trong `SignalRepository.create()`:

```python
mom_direction=data.get("mom_direction"),
```

Thêm regression tests tối thiểu:
- `TradingViewWebhookPayload` giữ được `metadata.mom_direction`
- `SignalNormalizer.normalize(...)` trả ra key `"mom_direction": -1`
- webhook payload thật có `mom_direction=-1` không bị `SQ_BAD_MOM_DIRECTION`

### Step 0.3: Chạy test config hiện tại (regression check)

```bash
./.venv/bin/python -m pytest tests/unit/test_config_repo.py -v
```

### Step 0.4: Tạo `migrations/003_v11_upgrade.sql`

Tạo file `migrations/003_v11_upgrade.sql`:

```sql
-- Migration 002: v1.1 Upgrade — Reverify table + config defaults
-- Created: 2026-04-25

-- 1. Bảng reverify results (non-mutating audit log)
CREATE TABLE IF NOT EXISTS signal_reverify_results (
    id                 VARCHAR(36) PRIMARY KEY,
    signal_row_id      VARCHAR(36) NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    original_decision  VARCHAR(32) NOT NULL,
    reverify_decision  VARCHAR(32) NOT NULL,
    reverify_score     NUMERIC(6,2),
    reject_code        VARCHAR(64),
    decision_reason    TEXT,
    score_items        JSONB,
    filter_results     JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_reverify_signal_row_id
    ON signal_reverify_results(signal_row_id, created_at DESC);

-- 2. Add mom_direction to persisted signals.
-- Pine sends int (-1/0/1); nullable keeps backward compatibility for old rows.
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS mom_direction INTEGER;

-- 3. Seed V1.1 config keys vào DB (deep-merge với existing config)
-- Chỉ thêm keys mới, không ghi đè keys cũ
UPDATE system_configs
SET
    config_value = config_value || jsonb_build_object(
        'rr_tolerance_pct', 0.10,
        'rr_target_by_type', jsonb_build_object(
            'SHORT_SQUEEZE', 2.5,
            'SHORT_V73', 1.67,
            'LONG_V73', 1.67
        ),
        'score_pass_threshold', 75,
        'strategy_thresholds', jsonb_build_object(
            'SHORT_SQUEEZE', jsonb_build_object(
                'rsi_min', 35, 'rsi_slope_max', -2, 'kc_position_max', 0.55, 'atr_pct_min', 0.20
            ),
            'SHORT_V73', jsonb_build_object('rsi_min', 60, 'stoch_k_min', 70),
            'LONG_V73', jsonb_build_object('rsi_max', 35, 'stoch_k_max', 20)
        ),
        'rescoring', jsonb_build_object(
            'SHORT_SQUEEZE', jsonb_build_object(
                'base', 70,
                'bonuses', jsonb_build_object(
                    'vol_regime_breakout_imminent', 8, 'regime_weak_trend_down', 6,
                    'regime_strong_trend_down', 8, 'mom_direction_neg1', 5,
                    'squeeze_bars_ge_4', 3, 'squeeze_bars_ge_6', 5,
                    'rsi_ge_40', 4, 'rsi_slope_le_neg4', 4,
                    'atr_percentile_ge_70', 3, 'kc_position_le_040', 3, 'confidence_ge_090', 3
                ),
                'penalties', jsonb_build_object(
                    'regime_strong_trend_up', -15, 'regime_weak_trend_up', -8,
                    'rsi_lt_35', -8, 'atr_pct_lt_020', -8, 'atr_pct_gt_150', -5
                )
            ),
            'SHORT_V73', jsonb_build_object(
                'base', 72,
                'bonuses', jsonb_build_object(
                    'rsi_ge_70', 5, 'stoch_ge_85', 5,
                    'rsi_slope_le_neg4', 4, 'regime_trend_down', 6, 'confidence_ge_090', 3
                ),
                'penalties', jsonb_build_object(
                    'regime_strong_trend_up', -15, 'vol_ranging_high', -6, 'atr_pct_lt_020', -6
                )
            ),
            'LONG_V73', jsonb_build_object(
                'base', 72,
                'bonuses', jsonb_build_object(
                    'rsi_le_25', 5, 'stoch_le_10', 5,
                    'rsi_slope_ge_2', 4, 'regime_trend_up', 6, 'confidence_ge_090', 3
                ),
                'penalties', jsonb_build_object(
                    'regime_strong_trend_down', -15, 'vol_ranging_high', -6, 'atr_pct_lt_020', -6
                )
            )
        )
    )
WHERE config_key = 'signal_bot_config'
  AND NOT (config_value ? 'strategy_thresholds');
-- ? operator kiểm tra key đã tồn tại chưa — chỉ insert nếu chưa có
-- (Không dùng ON CONFLICT vì config_value là JSONB, không phải JSONB bảng)
```

**Lưu ý quan trọng:** Migration dùng `||` (jsonb concat) thay vì `ON CONFLICT` vì `config_value` là JSONB column. Check `NOT (config_value ? 'strategy_thresholds')` đảm bảo idempotent — nếu V1.1 keys đã tồn tại thì không ghi đè.

**Lưu ý partial state:** Nếu production DB từng được update tay và đã có `strategy_thresholds` nhưng thiếu `rescoring` hoặc `rr_target_by_type`, câu `UPDATE` ở trên sẽ bỏ qua. Trước deploy cần verify bằng query JSONB và reconcile thủ công nếu DB đang ở trạng thái partial.

### Step 0.5: Commit

```bash
git add migrations/003_v11_upgrade.sql app/repositories/config_repo.py app/domain/schemas.py app/services/signal_normalizer.py app/domain/models.py app/repositories/signal_repo.py
git commit -m "config: add v1.1 defaults and mom_direction plumbing"
```

---

## Task 1: Reject Code Taxonomy

**Mục tiêu:** Central taxonomy cho reject codes — map từ rule_code → reject_code

### Step 1.1: Viết test

Tạo `tests/unit/test_reject_codes.py`:

```python
from app.services.reject_codes import RejectCode, rule_code_to_reject_code


def test_known_rule_codes_have_reject_codes():
    assert rule_code_to_reject_code("SYMBOL_ALLOWED") == RejectCode.INVALID_SYMBOL
    assert rule_code_to_reject_code("TIMEFRAME_ALLOWED") == RejectCode.UNSUPPORTED_TIMEFRAME
    assert rule_code_to_reject_code("DIRECTION_SANITY_VALID") == RejectCode.INVALID_PRICE_STRUCTURE
    assert rule_code_to_reject_code("MIN_RR_REQUIRED") == RejectCode.INVALID_RR_PROFILE
    assert rule_code_to_reject_code("MIN_CONFIDENCE_BY_TF") == RejectCode.LOW_CONFIDENCE
    assert rule_code_to_reject_code("DUPLICATE_SUPPRESSION") == RejectCode.DUPLICATE_SIGNAL
    assert rule_code_to_reject_code("NEWS_BLOCK") == RejectCode.NEWS_BLOCKED
    assert rule_code_to_reject_code("REGIME_HARD_BLOCK") == RejectCode.COUNTER_TREND_HARD
    assert rule_code_to_reject_code("SQ_NO_FIRED") == RejectCode.SQ_NO_FIRED
    assert rule_code_to_reject_code("SQ_BAD_MOM_DIRECTION") == RejectCode.SQ_BAD_MOM_DIRECTION
    assert rule_code_to_reject_code("SQ_BAD_VOL_REGIME") == RejectCode.SQ_BAD_VOL_REGIME
    assert rule_code_to_reject_code("SQ_BAD_STRATEGY_NAME") == RejectCode.SQ_BAD_STRATEGY_NAME
    assert rule_code_to_reject_code("S_BASE_BAD_STRATEGY_NAME") == RejectCode.S_BASE_BAD_STRATEGY_NAME
    assert rule_code_to_reject_code("L_BASE_BAD_STRATEGY_NAME") == RejectCode.L_BASE_BAD_STRATEGY_NAME
    assert rule_code_to_reject_code("RR_PROFILE_MATCH") == RejectCode.RR_PROFILE_MISMATCH
    assert rule_code_to_reject_code("BACKEND_SCORE_THRESHOLD") == RejectCode.BACKEND_SCORE_TOO_LOW


def test_unknown_rule_code_returns_generic():
    assert rule_code_to_reject_code("SOMETHING_NEW") == RejectCode.UNKNOWN
```

### Step 1.2: Chạy test → phải FAIL (ModuleNotFoundError)

```bash
./.venv/bin/python -m pytest tests/unit/test_reject_codes.py -v
```

### Step 1.3: Implement `app/services/reject_codes.py`

```python
from __future__ import annotations
from enum import Enum


class RejectCode(str, Enum):
    # Hard validation
    INVALID_SYMBOL = "INVALID_SYMBOL"
    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    INVALID_PRICE_STRUCTURE = "INVALID_PRICE_STRUCTURE"
    INVALID_NUMERIC_RANGE = "INVALID_NUMERIC_RANGE"
    INVALID_RR_PROFILE = "INVALID_RR_PROFILE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    # Business
    DUPLICATE_SIGNAL = "DUPLICATE_SIGNAL"
    NEWS_BLOCKED = "NEWS_BLOCKED"
    COUNTER_TREND_HARD = "COUNTER_TREND_HARD"
    # Strategy — SHORT_SQUEEZE
    SQ_NO_FIRED = "SQ_NO_FIRED"
    SQ_BAD_MOM_DIRECTION = "SQ_BAD_MOM_DIRECTION"
    SQ_BAD_VOL_REGIME = "SQ_BAD_VOL_REGIME"
    SQ_BAD_STRATEGY_NAME = "SQ_BAD_STRATEGY_NAME"
    SQ_RSI_TOO_LOW = "SQ_RSI_TOO_LOW"
    SQ_KC_POSITION_TOO_HIGH = "SQ_KC_POSITION_TOO_HIGH"
    # Strategy — SHORT_V73
    S_BASE_BAD_STRATEGY_NAME = "S_BASE_BAD_STRATEGY_NAME"
    S_BASE_RSI_TOO_LOW = "S_BASE_RSI_TOO_LOW"
    S_BASE_STOCH_TOO_LOW = "S_BASE_STOCH_TOO_LOW"
    # Strategy — LONG_V73
    L_BASE_BAD_STRATEGY_NAME = "L_BASE_BAD_STRATEGY_NAME"
    L_BASE_RSI_TOO_HIGH = "L_BASE_RSI_TOO_HIGH"
    L_BASE_STOCH_TOO_HIGH = "L_BASE_STOCH_TOO_HIGH"
    # V1.1 new rules
    RR_PROFILE_MISMATCH = "RR_PROFILE_MISMATCH"
    BACKEND_SCORE_TOO_LOW = "BACKEND_SCORE_TOO_LOW"
    # Unknown
    UNKNOWN = "UNKNOWN"


_RULE_TO_REJECT: dict[str, RejectCode] = {
    # Existing V1.0 rules
    "SYMBOL_ALLOWED": RejectCode.INVALID_SYMBOL,
    "TIMEFRAME_ALLOWED": RejectCode.UNSUPPORTED_TIMEFRAME,
    "PRICE_VALID": RejectCode.INVALID_NUMERIC_RANGE,
    "DIRECTION_SANITY_VALID": RejectCode.INVALID_PRICE_STRUCTURE,
    "MIN_RR_REQUIRED": RejectCode.INVALID_RR_PROFILE,
    "CONFIDENCE_RANGE_VALID": RejectCode.LOW_CONFIDENCE,
    "MIN_CONFIDENCE_BY_TF": RejectCode.LOW_CONFIDENCE,
    "DUPLICATE_SUPPRESSION": RejectCode.DUPLICATE_SIGNAL,
    "NEWS_BLOCK": RejectCode.NEWS_BLOCKED,
    "REGIME_HARD_BLOCK": RejectCode.COUNTER_TREND_HARD,
    # V1.1 strategy — SHORT_SQUEEZE
    "SQ_NO_FIRED": RejectCode.SQ_NO_FIRED,
    "SQ_BAD_MOM_DIRECTION": RejectCode.SQ_BAD_MOM_DIRECTION,
    "SQ_BAD_VOL_REGIME": RejectCode.SQ_BAD_VOL_REGIME,
    "SQ_BAD_STRATEGY_NAME": RejectCode.SQ_BAD_STRATEGY_NAME,
    "SQ_RSI_FLOOR": RejectCode.SQ_RSI_TOO_LOW,
    "SQ_KC_POSITION_FLOOR": RejectCode.SQ_KC_POSITION_TOO_HIGH,
    # V1.1 strategy — SHORT_V73
    "S_BASE_BAD_STRATEGY_NAME": RejectCode.S_BASE_BAD_STRATEGY_NAME,
    "S_BASE_RSI_FLOOR": RejectCode.S_BASE_RSI_TOO_LOW,
    "S_BASE_STOCH_FLOOR": RejectCode.S_BASE_STOCH_TOO_LOW,
    # V1.1 strategy — LONG_V73
    "L_BASE_BAD_STRATEGY_NAME": RejectCode.L_BASE_BAD_STRATEGY_NAME,
    "L_BASE_RSI_FLOOR": RejectCode.L_BASE_RSI_TOO_HIGH,
    "L_BASE_STOCH_FLOOR": RejectCode.L_BASE_STOCH_TOO_HIGH,
    # V1.1 new rules
    "RR_PROFILE_MATCH": RejectCode.RR_PROFILE_MISMATCH,
    "BACKEND_SCORE_THRESHOLD": RejectCode.BACKEND_SCORE_TOO_LOW,
}


def rule_code_to_reject_code(rule_code: str) -> RejectCode:
    return _RULE_TO_REJECT.get(rule_code, RejectCode.UNKNOWN)
```

### Step 1.4: Chạy test → phải PASS

```bash
./.venv/bin/python -m pytest tests/unit/test_reject_codes.py -v
```

### Step 1.5: Commit

```bash
git add app/services/reject_codes.py tests/unit/test_reject_codes.py
git commit -m "feat(reject-codes): add central taxonomy + rule_code mapping"
```

---

## Task 2: Strategy Validator — SHORT_SQUEEZE

**Mục tiêu:** Validate SHORT_SQUEEZE signals — hard rules (FAIL) + quality floors (WARN)

### Step 2.1: Viết tests

Tạo `tests/unit/test_strategy_validator.py`:

```python
from app.services.strategy_validator import validate_strategy
from app.core.enums import RuleResult, RuleSeverity


def _config():
    return {
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {
                "rsi_min": 35,
                "rsi_slope_max": -2,
                "kc_position_max": 0.55,
                "atr_pct_min": 0.20,
            },
            "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
            "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
        }
    }


def _sq_signal(**overrides):
    base = {
        "side": "SHORT",
        "signal_type": "SHORT_SQUEEZE",
        "strategy": "KELTNER_SQUEEZE",
        "squeeze_fired": 1,      # Pine gửi int, ORM là bool — validator xử lý cả 2
        "mom_direction": -1,       # Pine gửi int (-1/0/1)
        "vol_regime": "BREAKOUT_IMMINENT",
        "rsi": 37.5,
        "rsi_slope": -5.7,
        "kc_position": 0.31,
        "atr_pct": 0.49,
    }
    base.update(overrides)
    return base


def test_short_squeeze_pass():
    results = validate_strategy(_sq_signal(), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["SQ_NO_FIRED"].result == RuleResult.PASS
    assert codes["SQ_BAD_MOM_DIRECTION"].result == RuleResult.PASS
    assert codes["SQ_BAD_VOL_REGIME"].result == RuleResult.PASS
    assert codes["SQ_BAD_STRATEGY_NAME"].result == RuleResult.PASS
    assert codes["SQ_RSI_FLOOR"].result == RuleResult.PASS
    assert codes["SQ_KC_POSITION_FLOOR"].result == RuleResult.PASS


def test_short_squeeze_fail_not_fired():
    # squeeze_fired có thể là 0 (int) hoặc False (bool)
    for val in [0, False]:
        results = validate_strategy(_sq_signal(squeeze_fired=val), _config())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_NO_FIRED"].result == RuleResult.FAIL
        assert codes["SQ_NO_FIRED"].severity == RuleSeverity.HIGH


def test_short_squeeze_fail_bad_momentum():
    # mom_direction: Pine gửi int, có thể là 1 hoặc -1
    for val in [1, 0]:  # sai, phải là -1
        results = validate_strategy(_sq_signal(mom_direction=val), _config())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_BAD_MOM_DIRECTION"].result == RuleResult.FAIL


def test_short_squeeze_fail_bad_vol_regime():
    for bad_regime in ["TRENDING_LOW_VOL", "RANGING_HIGH_VOL", "SQUEEZE_BUILDING"]:
        results = validate_strategy(_sq_signal(vol_regime=bad_regime), _config())
        codes = {r.rule_code: r for r in results}
        assert codes["SQ_BAD_VOL_REGIME"].result == RuleResult.FAIL


def test_short_squeeze_fail_bad_strategy_name():
    results = validate_strategy(_sq_signal(strategy="RSI_STOCH_V73"), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["SQ_BAD_STRATEGY_NAME"].result == RuleResult.FAIL


def test_short_squeeze_warn_rsi_floor():
    # rsi < rsi_min (35) → WARN
    results = validate_strategy(_sq_signal(rsi=30), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["SQ_RSI_FLOOR"].result == RuleResult.WARN
    assert codes["SQ_RSI_FLOOR"].severity == RuleSeverity.MEDIUM


def test_short_squeeze_warn_kc_position_floor():
    # kc_position > kc_position_max (0.55) → WARN
    results = validate_strategy(_sq_signal(kc_position=0.80), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["SQ_KC_POSITION_FLOOR"].result == RuleResult.WARN
```

**Lưu ý quan trọng:**
- `squeeze_fired`: Pine gửi `int (0/1)`, ORM model có `Boolean`. Validator phải xử lý cả hai: `squeeze_fired in (1, True)`
- `mom_direction`: Pine gửi `int (-1/0/1)`, validator check `!= -1` là FAIL

### Step 2.2: Chạy test → FAIL (ModuleNotFoundError)

```bash
./.venv/bin/python -m pytest tests/unit/test_strategy_validator.py -v
```

### Step 2.3: Implement `app/services/strategy_validator.py`

```python
from __future__ import annotations
from typing import Any
from app.services.filter_engine import FilterResult
from app.core.enums import RuleResult, RuleSeverity


_GROUP = "strategy"


def _pass(code: str) -> FilterResult:
    return FilterResult(code, _GROUP, RuleResult.PASS, RuleSeverity.INFO)


def _fail(code: str, details: dict | None = None) -> FilterResult:
    return FilterResult(code, _GROUP, RuleResult.FAIL, RuleSeverity.HIGH, 0.0, details)


def _warn(code: str, details: dict | None = None) -> FilterResult:
    # Pilot: quality floor rules = WARN MEDIUM (không FAIL)
    return FilterResult(code, _GROUP, RuleResult.WARN, RuleSeverity.MEDIUM, 0.0, details)


def validate_strategy(signal: dict, config: dict) -> list[FilterResult]:
    signal_type = signal.get("signal_type")
    if signal_type == "SHORT_SQUEEZE":
        return _validate_short_squeeze(signal, config)
    if signal_type == "SHORT_V73":
        return _validate_short_v73(signal, config)
    if signal_type == "LONG_V73":
        return _validate_long_v73(signal, config)
    return []


def _validate_short_squeeze(signal: dict, config: dict) -> list[FilterResult]:
    th = config.get("strategy_thresholds", {}).get("SHORT_SQUEEZE", {})
    out: list[FilterResult] = []

    # squeeze_fired: Pine gửi int (0/1), ORM là bool → check cả 2
    squeeze_fired = signal.get("squeeze_fired")
    squeeze_ok = squeeze_fired in (1, True)
    out.append(_fail("SQ_NO_FIRED") if not squeeze_ok else _pass("SQ_NO_FIRED"))

    # mom_direction: Pine gửi int (-1/0/1)
    mom = signal.get("mom_direction")
    out.append(
        _fail("SQ_BAD_MOM_DIRECTION", {"mom_direction": mom})
        if mom != -1
        else _pass("SQ_BAD_MOM_DIRECTION")
    )

    # vol_regime phải là BREAKOUT_IMMINENT
    vol_regime = signal.get("vol_regime")
    out.append(
        _fail("SQ_BAD_VOL_REGIME", {"vol_regime": vol_regime})
        if vol_regime != "BREAKOUT_IMMINENT"
        else _pass("SQ_BAD_VOL_REGIME")
    )

    # strategy phải là KELTNER_SQUEEZE
    strategy = signal.get("strategy")
    out.append(
        _fail("SQ_BAD_STRATEGY_NAME", {"strategy": strategy})
        if strategy != "KELTNER_SQUEEZE"
        else _pass("SQ_BAD_STRATEGY_NAME")
    )

    # Quality floor: RSI ≥ rsi_min → WARN nếu thấp hơn
    rsi = signal.get("rsi")
    rsi_min = th.get("rsi_min", 35)
    if rsi is not None and rsi < rsi_min:
        out.append(_warn("SQ_RSI_FLOOR", {"rsi": rsi, "min": rsi_min}))
    else:
        out.append(_pass("SQ_RSI_FLOOR"))

    # Quality floor: kc_position ≤ kc_position_max → WARN nếu cao hơn
    kc = signal.get("kc_position")
    kc_max = th.get("kc_position_max", 0.55)
    if kc is not None and kc > kc_max:
        out.append(_warn("SQ_KC_POSITION_FLOOR", {"kc_position": kc, "max": kc_max}))
    else:
        out.append(_pass("SQ_KC_POSITION_FLOOR"))

    return out


def _validate_short_v73(signal: dict, config: dict) -> list[FilterResult]:
    return []  # Task 3


def _validate_long_v73(signal: dict, config: dict) -> list[FilterResult]:
    return []  # Task 3
```

### Step 2.4: Chạy test → 7 tests PASS

```bash
./.venv/bin/python -m pytest tests/unit/test_strategy_validator.py -v
```

### Step 2.5: Commit

```bash
git add app/services/strategy_validator.py tests/unit/test_strategy_validator.py
git commit -m "feat(strategy): add SHORT_SQUEEZE validator with hard rules + quality floors"
```

---

## Task 3: Strategy Validator — SHORT_V73 + LONG_V73

**Mục tiêu:** Hoàn thiện strategy validation cho SHORT_V73 và LONG_V73

### Step 3.1: Append tests cho SHORT_V73 + LONG_V73

Thêm vào `tests/unit/test_strategy_validator.py`:

```python
def _sv73_signal(**overrides):
    base = {
        "side": "SHORT",
        "signal_type": "SHORT_V73",
        "strategy": "RSI_STOCH_V73",
        "rsi": 72,
        "stoch_k": 80,
    }
    base.update(overrides)
    return base


def test_short_v73_pass():
    results = validate_strategy(_sv73_signal(), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["S_BASE_BAD_STRATEGY_NAME"].result == RuleResult.PASS
    assert codes["S_BASE_RSI_FLOOR"].result == RuleResult.PASS
    assert codes["S_BASE_STOCH_FLOOR"].result == RuleResult.PASS


def test_short_v73_fail_strategy_name():
    results = validate_strategy(_sv73_signal(strategy="KELTNER_SQUEEZE"), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["S_BASE_BAD_STRATEGY_NAME"].result == RuleResult.FAIL


def test_short_v73_warn_rsi_floor():
    # rsi < rsi_min (60) → WARN
    results = validate_strategy(_sv73_signal(rsi=55), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["S_BASE_RSI_FLOOR"].result == RuleResult.WARN


def test_short_v73_warn_stoch_floor():
    # stoch_k < stoch_k_min (70) → WARN
    results = validate_strategy(_sv73_signal(stoch_k=61), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["S_BASE_STOCH_FLOOR"].result == RuleResult.WARN


def _lv73_signal(**overrides):
    base = {
        "side": "LONG",
        "signal_type": "LONG_V73",
        "strategy": "RSI_STOCH_V73",
        "rsi": 28,
        "stoch_k": 15,
    }
    base.update(overrides)
    return base


def test_long_v73_pass():
    results = validate_strategy(_lv73_signal(), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["L_BASE_BAD_STRATEGY_NAME"].result == RuleResult.PASS
    assert codes["L_BASE_RSI_FLOOR"].result == RuleResult.PASS
    assert codes["L_BASE_STOCH_FLOOR"].result == RuleResult.PASS


def test_long_v73_fail_strategy_name():
    results = validate_strategy(_lv73_signal(strategy="KELTNER_SQUEEZE"), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["L_BASE_BAD_STRATEGY_NAME"].result == RuleResult.FAIL


def test_long_v73_warn_rsi_floor():
    # rsi > rsi_max (35) → WARN (RSI quá cao cho LONG)
    results = validate_strategy(_lv73_signal(rsi=41), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["L_BASE_RSI_FLOOR"].result == RuleResult.WARN


def test_long_v73_warn_stoch_floor():
    # stoch_k > stoch_k_max (20) → WARN (Stoch quá cao cho LONG)
    results = validate_strategy(_lv73_signal(stoch_k=25), _config())
    codes = {r.rule_code: r for r in results}
    assert codes["L_BASE_STOCH_FLOOR"].result == RuleResult.WARN


def test_unknown_signal_type_returns_empty():
    assert validate_strategy({"signal_type": "XYZ"}, _config()) == []
```

### Step 3.2: Chạy test → 8 tests FAIL (placeholder methods)

```bash
./.venv/bin/python -m pytest tests/unit/test_strategy_validator.py -v
```

### Step 3.3: Implement `_validate_short_v73` và `_validate_long_v73`

Thay placeholder trong `app/services/strategy_validator.py`:

```python
def _validate_short_v73(signal: dict, config: dict) -> list[FilterResult]:
    th = config.get("strategy_thresholds", {}).get("SHORT_V73", {})
    out: list[FilterResult] = []

    out.append(
        _fail("S_BASE_BAD_STRATEGY_NAME", {"strategy": signal.get("strategy")})
        if signal.get("strategy") != "RSI_STOCH_V73"
        else _pass("S_BASE_BAD_STRATEGY_NAME")
    )

    # RSI floor: SHORT cần RSI đủ cao (≥ rsi_min)
    rsi = signal.get("rsi")
    rsi_min = th.get("rsi_min", 60)
    if rsi is not None and rsi < rsi_min:
        out.append(_warn("S_BASE_RSI_FLOOR", {"rsi": rsi, "min": rsi_min}))
    else:
        out.append(_pass("S_BASE_RSI_FLOOR"))

    # Stoch floor: SHORT cần Stoch đủ cao (≥ stoch_k_min)
    stoch = signal.get("stoch_k")
    stoch_min = th.get("stoch_k_min", 70)
    if stoch is not None and stoch < stoch_min:
        out.append(_warn("S_BASE_STOCH_FLOOR", {"stoch_k": stoch, "min": stoch_min}))
    else:
        out.append(_pass("S_BASE_STOCH_FLOOR"))

    return out


def _validate_long_v73(signal: dict, config: dict) -> list[FilterResult]:
    th = config.get("strategy_thresholds", {}).get("LONG_V73", {})
    out: list[FilterResult] = []

    out.append(
        _fail("L_BASE_BAD_STRATEGY_NAME", {"strategy": signal.get("strategy")})
        if signal.get("strategy") != "RSI_STOCH_V73"
        else _pass("L_BASE_BAD_STRATEGY_NAME")
    )

    # RSI floor: LONG cần RSI đủ thấp (≤ rsi_max)
    rsi = signal.get("rsi")
    rsi_max = th.get("rsi_max", 35)
    if rsi is not None and rsi > rsi_max:
        out.append(_warn("L_BASE_RSI_FLOOR", {"rsi": rsi, "max": rsi_max}))
    else:
        out.append(_pass("L_BASE_RSI_FLOOR"))

    # Stoch floor: LONG cần Stoch đủ thấp (≤ stoch_k_max)
    stoch = signal.get("stoch_k")
    stoch_max = th.get("stoch_k_max", 20)
    if stoch is not None and stoch > stoch_max:
        out.append(_warn("L_BASE_STOCH_FLOOR", {"stoch_k": stoch, "max": stoch_max}))
    else:
        out.append(_pass("L_BASE_STOCH_FLOOR"))

    return out
```

### Step 3.4: Cập nhật `reject_codes.py` (thêm 6 quality floor codes)

Thêm vào `RejectCode` enum và `_RULE_TO_REJECT` map (đã làm ở Task 1 rồi, verify lại).

### Step 3.5: Chạy full unit tests

```bash
./.venv/bin/python -m pytest tests/unit -v
```

### Step 3.6: Commit

```bash
git add app/services/strategy_validator.py app/services/reject_codes.py tests/unit/test_strategy_validator.py
git commit -m "feat(strategy): add SHORT_V73 + LONG_V73 validators; expand reject taxonomy"
```

---

## Task 4: Rescoring Engine

**Mục tiêu:** Backend rescoring với config-driven bonus/penalty table

### Step 4.1: Viết tests

Tạo `tests/unit/test_rescoring_engine.py`:

```python
from app.services.rescoring_engine import rescore


def _cfg():
    return {
        "rescoring": {
            "SHORT_SQUEEZE": {
                "base": 70,
                "bonuses": {
                    "vol_regime_breakout_imminent": 8,
                    "regime_weak_trend_down": 6,
                    "regime_strong_trend_down": 8,
                    "mom_direction_neg1": 5,
                    "squeeze_bars_ge_4": 3,
                    "squeeze_bars_ge_6": 5,
                    "rsi_ge_40": 4,
                    "rsi_slope_le_neg4": 4,
                    "atr_percentile_ge_70": 3,
                    "kc_position_le_040": 3,
                    "confidence_ge_090": 3,
                },
                "penalties": {
                    "regime_strong_trend_up": -15,
                    "regime_weak_trend_up": -8,
                    "rsi_lt_35": -8,
                    "atr_pct_lt_020": -8,
                    "atr_pct_gt_150": -5,
                },
            },
            "SHORT_V73": {
                "base": 72,
                "bonuses": {"rsi_ge_70": 5, "stoch_ge_85": 5, "confidence_ge_090": 3},
                "penalties": {"regime_strong_trend_up": -15},
            },
            "LONG_V73": {
                "base": 72,
                "bonuses": {"rsi_le_25": 5, "stoch_le_10": 5, "confidence_ge_090": 3},
                "penalties": {"regime_strong_trend_down": -15},
            },
        }
    }


def test_short_squeeze_sample_signal_scores_correctly():
    # Sample: conf=0.90, WEAK_TREND_DOWN, BREAKOUT_IMMINENT,
    # mom=-1, squeeze_bars=6, rsi=37.5, rsi_slope=-5.7, atr_percentile=78,
    # kc_position=0.31, atr_pct=0.49
    signal = {
        "signal_type": "SHORT_SQUEEZE",
        "indicator_confidence": 0.90,
        "regime": "WEAK_TREND_DOWN",
        "vol_regime": "BREAKOUT_IMMINENT",
        "mom_direction": -1,
        "squeeze_bars": 6,
        "rsi": 37.5,
        "rsi_slope": -5.7,
        "atr_percentile": 78,
        "kc_position": 0.31,
        "atr_pct": 0.49,
    }
    score, items = rescore(signal, _cfg())
    # 70 + 8 (breakout) + 6 (weak_trend_down) + 5 (mom=-1) + 3 (bars>=4) + 5 (bars>=6)
    # + 4 (rsi_slope<=-4) + 3 (atr_pct>=70) + 3 (kc<=0.40) + 3 (conf>=0.90) = 110 → clamp 100
    assert score == 100
    assert any("vol_regime_breakout_imminent" in it for it in items)


def test_short_squeeze_penalty_applies():
    signal = {
        "signal_type": "SHORT_SQUEEZE",
        "indicator_confidence": 0.80,
        "regime": "STRONG_TREND_UP",
        "vol_regime": "TRENDING_LOW_VOL",
        "mom_direction": 1,
        "rsi": 30,
        "atr_pct": 0.10,
    }
    score, _ = rescore(signal, _cfg())
    # 70 - 15 (strong_up) - 8 (rsi<35) - 8 (atr<0.20) = 39
    assert score == 39


def test_short_v73_base_and_bonus():
    signal = {
        "signal_type": "SHORT_V73",
        "indicator_confidence": 0.91,
        "regime": "WEAK_TREND_DOWN",
        "rsi": 72,
        "stoch_k": 88,
    }
    score, _ = rescore(signal, _cfg())
    # 72 + 5 (rsi>=70) + 5 (stoch>=85) + 3 (conf>=0.90) = 85
    assert score == 85


def test_long_v73_base_and_bonus():
    signal = {
        "signal_type": "LONG_V73",
        "indicator_confidence": 0.92,
        "rsi": 24,
        "stoch_k": 8,
    }
    score, _ = rescore(signal, _cfg())
    # 72 + 5 (rsi<=25) + 5 (stoch<=10) + 3 (conf>=0.90) = 85
    assert score == 85


def test_unknown_signal_type_falls_back_to_base_70():
    signal = {"signal_type": "UNKNOWN_X"}
    score, items = rescore(signal, _cfg())
    assert score == 70
    assert items == ["base_fallback=70"]


def test_score_clamped_to_0_100():
    signal = {
        "signal_type": "SHORT_SQUEEZE",
        "indicator_confidence": 0.0,
        "regime": "STRONG_TREND_UP",
        "mom_direction": 1,
        "rsi": 10,
        "atr_pct": 0.05,
        "vol_regime": "RANGING_HIGH_VOL",
    }
    score, _ = rescore(signal, _cfg())
    assert 0 <= score <= 100
```

### Step 4.2: Chạy test → FAIL (ModuleNotFoundError)

```bash
./.venv/bin/python -m pytest tests/unit/test_rescoring_engine.py -v
```

### Step 4.3: Implement `app/services/rescoring_engine.py`

```python
from __future__ import annotations
from typing import Any


def rescore(signal: dict, config: dict) -> tuple[int, list[str]]:
    """Return (final_score_0_to_100, breakdown_items_as_strings)."""
    signal_type = signal.get("signal_type")
    rs_cfg = config.get("rescoring", {}).get(signal_type)
    if not rs_cfg:
        return 70, ["base_fallback=70"]

    score = int(rs_cfg.get("base", 70))
    items: list[str] = [f"base={score}"]
    bonuses = rs_cfg.get("bonuses", {})
    penalties = rs_cfg.get("penalties", {})

    applied = _collect_applied_rules(signal)

    for key, delta in bonuses.items():
        if key in applied:
            score += int(delta)
            items.append(f"{key}+{delta}")

    for key, delta in penalties.items():
        if key in applied:
            score += int(delta)
            items.append(f"{key}{delta}")

    score = max(0, min(100, score))
    return score, items


def _collect_applied_rules(signal: dict) -> set[str]:
    rules: set[str] = set()

    conf = _num(signal.get("indicator_confidence"))
    regime = signal.get("regime")
    vol_regime = signal.get("vol_regime")
    mom = signal.get("mom_direction")
    squeeze_bars = _num(signal.get("squeeze_bars"))
    rsi = _num(signal.get("rsi"))
    rsi_slope = _num(signal.get("rsi_slope"))
    stoch_k = _num(signal.get("stoch_k"))
    atr_percentile = _num(signal.get("atr_percentile"))
    kc = _num(signal.get("kc_position"))
    atr_pct = _num(signal.get("atr_pct"))

    if vol_regime == "BREAKOUT_IMMINENT":
        rules.add("vol_regime_breakout_imminent")
    if regime == "WEAK_TREND_DOWN":
        rules.add("regime_weak_trend_down")
        rules.add("regime_trend_down")
    if regime == "STRONG_TREND_DOWN":
        rules.add("regime_strong_trend_down")
        rules.add("regime_trend_down")
    if regime == "WEAK_TREND_UP":
        rules.add("regime_weak_trend_up")
        rules.add("regime_trend_up")
    if regime == "STRONG_TREND_UP":
        rules.add("regime_strong_trend_up")
        rules.add("regime_trend_up")
    if vol_regime == "RANGING_HIGH_VOL":
        rules.add("vol_ranging_high")
    if mom == -1:
        rules.add("mom_direction_neg1")

    if squeeze_bars is not None:
        if squeeze_bars >= 4:
            rules.add("squeeze_bars_ge_4")
        if squeeze_bars >= 6:
            rules.add("squeeze_bars_ge_6")

    if rsi is not None:
        if rsi >= 40:
            rules.add("rsi_ge_40")
        if rsi < 35:
            rules.add("rsi_lt_35")
        if rsi >= 70:
            rules.add("rsi_ge_70")
        if rsi <= 25:
            rules.add("rsi_le_25")

    if rsi_slope is not None:
        if rsi_slope <= -4:
            rules.add("rsi_slope_le_neg4")
        if rsi_slope >= 2:
            rules.add("rsi_slope_ge_2")

    if stoch_k is not None:
        if stoch_k >= 85:
            rules.add("stoch_ge_85")
        if stoch_k <= 10:
            rules.add("stoch_le_10")

    if atr_percentile is not None and atr_percentile >= 70:
        rules.add("atr_percentile_ge_70")

    if kc is not None and kc <= 0.40:
        rules.add("kc_position_le_040")

    if atr_pct is not None:
        if atr_pct < 0.20:
            rules.add("atr_pct_lt_020")
        if atr_pct > 1.50:
            rules.add("atr_pct_gt_150")

    if conf is not None and conf >= 0.90:
        rules.add("confidence_ge_090")

    return rules


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
```

### Step 4.4: Chạy test → 6 tests PASS

```bash
./.venv/bin/python -m pytest tests/unit/test_rescoring_engine.py -v
```

### Step 4.5: Commit

```bash
git add app/services/rescoring_engine.py tests/unit/test_rescoring_engine.py
git commit -m "feat(rescoring): backend scoring engine with config-driven bonuses/penalties"
```

---

## Task 5: Integrate Strategy + Rescoring into FilterEngine

**Mục tiêu:** Tích hợp strategy validator, rescoring, và RR profile match vào filter engine

### Step 5.1: Viết integration tests trong `test_filter_engine.py`

Thêm vào cuối `tests/unit/test_filter_engine.py`:

```python
def _v11_config():
    return {
        "strategy_thresholds": {
            "SHORT_SQUEEZE": {"rsi_min": 35, "rsi_slope_max": -2, "kc_position_max": 0.55, "atr_pct_min": 0.20},
            "SHORT_V73": {"rsi_min": 60, "stoch_k_min": 70},
            "LONG_V73": {"rsi_max": 35, "stoch_k_max": 20},
        },
        "rescoring": {
            "SHORT_SQUEEZE": {
                "base": 70,
                "bonuses": {
                    "vol_regime_breakout_imminent": 8,
                    "regime_weak_trend_down": 6,
                    "mom_direction_neg1": 5,
                    "squeeze_bars_ge_6": 5,
                    "confidence_ge_090": 3,
                },
                "penalties": {"regime_strong_trend_up": -15},
            },
        },
        "score_pass_threshold": 75,
        "rr_tolerance_pct": 0.10,
        "rr_target_by_type": {"SHORT_SQUEEZE": 2.5, "SHORT_V73": 1.67, "LONG_V73": 1.67},
    }


def test_short_squeeze_pipeline_pass_main():
    """SHORT_SQUEEZE signal đạt đủ điều kiện → PASS_MAIN"""
    engine = make_filter_engine(_v11_config())
    signal = make_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        side="SHORT",
        entry_price=74988.60,
        stop_loss=75429.33,
        take_profit=73886.79,
        risk_reward=2.5,
        indicator_confidence=0.90,
        timeframe="15m",
        regime="WEAK_TREND_DOWN",
        vol_regime="BREAKOUT_IMMINENT",
        mom_direction=-1,
        squeeze_fired=1,
        squeeze_bars=6,
        rsi=37.5,
        rsi_slope=-5.7,
        kc_position=0.31,
        atr_pct=0.49,
    )
    result = engine.run(signal)
    assert result.final_decision == "PASS_MAIN"
    assert 0.0 <= result.server_score <= 1.0


def test_short_squeeze_reject_not_fired():
    """squeeze_fired=0 → SQ_NO_FIRED FAIL → REJECT"""
    engine = make_filter_engine(_v11_config())
    signal = make_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        side="SHORT",
        entry_price=74988.60,
        stop_loss=75429.33,
        take_profit=73886.79,
        risk_reward=2.5,
        indicator_confidence=0.90,
        timeframe="15m",
        squeeze_fired=0,  # ← reject
        mom_direction=-1,
        vol_regime="BREAKOUT_IMMINENT",
        rsi=37.5,
        kc_position=0.31,
        atr_pct=0.49,
    )
    result = engine.run(signal)
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "SQ_NO_FIRED" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_backend_score_threshold_warns_when_low():
    """Backend score < threshold → BACKEND_SCORE_THRESHOLD WARN → PASS_WARNING"""
    cfg = _v11_config()
    cfg["score_pass_threshold"] = 90  # Force low score to WARN
    engine = make_filter_engine(cfg)
    signal = make_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        side="SHORT",
        entry_price=74988.60,
        stop_loss=75429.33,
        take_profit=73886.79,
        risk_reward=2.5,
        indicator_confidence=0.80,  # thấp hơn → score sẽ thấp
        timeframe="15m",
        squeeze_fired=1,
        mom_direction=-1,
        vol_regime="BREAKOUT_IMMINENT",
        rsi=37.5,
        kc_position=0.31,
        atr_pct=0.49,
    )
    result = engine.run(signal)
    # BACKEND_SCORE_THRESHOLD phải là WARN (pilot mode)
    score_rule = next((r for r in result.filter_results if r.rule_code == "BACKEND_SCORE_THRESHOLD"), None)
    assert score_rule is not None
    assert score_rule.result.value == "WARN"
    assert score_rule.severity.value == "MEDIUM"
    # WARN MEDIUM → route sang WARN channel
    assert result.route.value == "WARN"


def test_rr_profile_match_warns_on_upper_bound():
    """RR cao hơn target+10% → RR_PROFILE_MATCH WARN (pilot) → PASS_WARNING"""
    engine = make_filter_engine(_v11_config())
    # SHORT_SQUEEZE target = 2.5, tolerance = 10%
    # upper bound = 2.5 * 1.10 = 2.75
    # RR = 3.0 > 2.75 → WARN (pilot)
    signal = make_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        side="SHORT",
        entry_price=100.0,
        stop_loss=101.0,
        take_profit=97.0,  # reward=3.0, risk=1.0, rr=3.0
        risk_reward=3.0,
        indicator_confidence=0.90,
        timeframe="15m",
        squeeze_fired=1,
        mom_direction=-1,
        vol_regime="BREAKOUT_IMMINENT",
        rsi=37.5,
        kc_position=0.31,
        atr_pct=0.49,
    )
    result = engine.run(signal)
    rr_rule = next((r for r in result.filter_results if r.rule_code == "RR_PROFILE_MATCH"), None)
    assert rr_rule is not None
    assert rr_rule.result.value == "WARN"  # pilot: WARN not FAIL
    assert rr_rule.severity.value == "MEDIUM"
    # Có WARN MEDIUM → PASS_WARNING
    assert result.final_decision.value == "PASS_WARNING"


def test_min_rr_still_enforces_lower_bound():
    """MIN_RR_REQUIRED (lower-bound) vẫn FAIL nếu RR quá thấp"""
    engine = make_filter_engine(_v11_config())
    signal = make_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        side="SHORT",
        entry_price=100.0,
        stop_loss=101.0,
        take_profit=100.8,  # rr = 0.8/1.0 = 0.8 < 1.5 (lo)
        risk_reward=0.8,
        indicator_confidence=0.90,
        timeframe="15m",
        squeeze_fired=1,
        mom_direction=-1,
        vol_regime="BREAKOUT_IMMINENT",
        rsi=37.5,
        kc_position=0.31,
        atr_pct=0.49,
    )
    result = engine.run(signal)
    fail_codes = [r.rule_code for r in result.filter_results if r.result.value == "FAIL"]
    assert "MIN_RR_REQUIRED" in fail_codes
    assert result.final_decision.value == "REJECT"


def test_rsi_floor_warns_pilot():
    """RSI floor < threshold → SQ_RSI_FLOOR WARN → PASS_WARNING"""
    engine = make_filter_engine(_v11_config())
    signal = make_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        side="SHORT",
        entry_price=100.0,
        stop_loss=101.0,
        take_profit=97.0,
        risk_reward=3.0,
        indicator_confidence=0.90,
        timeframe="15m",
        squeeze_fired=1,
        mom_direction=-1,
        vol_regime="BREAKOUT_IMMINENT",
        rsi=30,  # < 35 → WARN
        kc_position=0.31,
        atr_pct=0.49,
    )
    result = engine.run(signal)
    rsi_rule = next((r for r in result.filter_results if r.rule_code == "SQ_RSI_FLOOR"), None)
    assert rsi_rule is not None
    assert rsi_rule.result.value == "WARN"
    assert rsi_rule.severity.value == "MEDIUM"
    assert result.final_decision.value == "PASS_WARNING"
```

### Step 5.2: Chạy test → phải FAIL (chưa integrate)

```bash
./.venv/bin/python -m pytest tests/unit/test_filter_engine.py -v
```

### Step 5.3: Cập nhật `filter_engine.py`

**5.3a. Thêm method `_check_rr_profile_match`** — Thêm vào cuối class (sau `_check_cooldown`):

```python
def _check_rr_profile_match(self, signal: dict, results: list[FilterResult]):
    """
    Pilot: RR profile match check.
    - RR ngoài target ± tolerance → WARN MEDIUM (không FAIL trong pilot)
    - Giữ MIN_RR_REQUIRED (lower-bound) không đổi
    """
    rr = signal.get("risk_reward")
    if rr is None:
        return

    signal_type = signal.get("signal_type")
    targets = self.config.get("rr_target_by_type", {})
    tolerance = self.config.get("rr_tolerance_pct", 0.10)

    if signal_type not in targets:
        return  # Unknown type → skip, MIN_RR_REQUIRED đã xử lý lower-bound

    target = float(targets[signal_type])
    lo = target * (1 - tolerance)
    hi = target * (1 + tolerance)

    if lo <= rr <= hi:
        results.append(FilterResult("RR_PROFILE_MATCH", "trading", RuleResult.PASS, RuleSeverity.INFO))
    else:
        # Pilot mode: WARN MEDIUM, không FAIL
        details = {"rr": rr, "target": target, "tolerance_pct": tolerance, "lo": lo, "hi": hi}
        results.append(FilterResult("RR_PROFILE_MATCH", "trading", RuleResult.WARN, RuleSeverity.MEDIUM, 0.0, details))
```

**5.3b. Cập nhật `run()` method** — Thêm Phase 2.5, Phase 3c và gọi `_check_rr_profile_match`:

Thay toàn bộ `run()` method:

```python
def run(self, signal: dict) -> FilterExecutionResult:
    from app.services.strategy_validator import validate_strategy
    from app.services.rescoring_engine import rescore

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
    self._check_min_rr(signal, results)  # Lower-bound check (unchanged)

    if self._has_fail(results):
        return self._build_result(results, signal, "Trade math failed")

    # Phase 2.5: Strategy-specific validation (V1.1 new)
    results.extend(validate_strategy(signal, self.config))
    if self._has_fail(results):
        return self._build_result(results, signal, "Strategy validation failed")

    # Phase 3a: Hard business rules (unchanged)
    self._check_min_confidence_by_tf(signal, results)
    self._check_duplicate(signal, results)
    self._check_news_block(signal, results)
    self._check_regime_hard_block(signal, results)

    if self._has_fail(results):
        return self._build_result(results, signal, "Business rule failed")

    # Phase 3b: Advisory warnings (unchanged)
    self._check_volatility(signal, results)
    self._check_cooldown(signal, results)
    self._check_low_volume(signal, results)

    # Phase 3c: RR profile match check (V1.1 new)
    self._check_rr_profile_match(signal, results)

    # Phase 3d: Backend rescoring + threshold (V1.1 new)
    backend_score, items = rescore(signal, self.config)
    threshold = self.config.get("score_pass_threshold", 75)
    if backend_score < threshold:
        # Pilot mode: WARN MEDIUM, không FAIL
        results.append(FilterResult(
            "BACKEND_SCORE_THRESHOLD", "rescoring", RuleResult.WARN, RuleSeverity.MEDIUM,
            0.0, {"score": backend_score, "threshold": threshold, "items": items},
        ))
    else:
        results.append(FilterResult(
            "BACKEND_SCORE_THRESHOLD", "rescoring", RuleResult.PASS, RuleSeverity.INFO,
            0.0, {"score": backend_score, "threshold": threshold, "items": items},
        ))

    # Phase 4: Route
    return self._build_result(results, signal, "Filters passed")
```

### Step 5.4: Chạy full unit tests

```bash
./.venv/bin/python -m pytest tests/unit -v
```

### Step 5.5: Commit

```bash
git add app/services/filter_engine.py tests/unit/test_filter_engine.py
git commit -m "feat(filter-engine): integrate strategy validator + rescoring + RR profile match"
```

---

## Task 6: Surface reject_code in Admin Telegram Message

**Mục tiêu:** Hiển thị reject_code chuẩn trong admin reject message

### Step 6.1: Viết test

Thêm vào `tests/unit/test_message_renderer.py`:

```python
def test_render_reject_admin_includes_reject_code():
    from app.services.message_renderer import MessageRenderer
    signal = {"symbol": "BTCUSD", "timeframe": "15m", "side": "SHORT", "signal_id": "x"}
    msg = MessageRenderer.render_reject_admin(
        signal,
        reason="Strategy validation failed: SQ_NO_FIRED",
        reject_code="SQ_NO_FIRED",
    )
    assert "SQ_NO_FIRED" in msg
    assert "RejectCode:" in msg


def test_render_reject_admin_no_reject_code():
    from app.services.message_renderer import MessageRenderer
    signal = {"symbol": "BTCUSD", "timeframe": "15m", "side": "SHORT", "signal_id": "x"}
    msg = MessageRenderer.render_reject_admin(
        signal,
        reason="Some error",
        reject_code=None,
    )
    assert "RejectCode:" not in msg
```

### Step 6.2: Chạy test → FAIL (unexpected kwarg)

```bash
./.venv/bin/python -m pytest tests/unit/test_message_renderer.py::test_render_reject_admin_includes_reject_code -v
```

### Step 6.3: Cập nhật `render_reject_admin` trong `app/services/message_renderer.py`

Thay `render_reject_admin` method (dòng 117-126):

```python
@staticmethod
def render_reject_admin(signal: dict, reason: str, reject_code: str | None = None) -> str:
    side = signal.get("side", "").upper()
    symbol = signal.get("symbol", "UNKNOWN")
    tf = signal.get("timeframe", "UNKNOWN")
    signal_id = signal.get("signal_id", "UNKNOWN")
    code_line = f"\nRejectCode: {reject_code}" if reject_code else ""

    return MessageRenderer._append_footer(f"""⛔ REJECTED | {symbol} {side} | {tf}{code_line}
Reason: {reason}
Signal ID: {signal_id}""")
```

### Step 6.4: Cập nhật `webhook_ingestion_service.py` để truyền reject_code

Trong `_build_notification_job()`, sửa REJECT branch:

```python
elif filter_result.final_decision == DecisionType.REJECT and config.get("log_reject_to_admin"):
    from app.services.reject_codes import rule_code_to_reject_code

    first_fail = next(
        (r for r in filter_result.filter_results if r.result.value == "FAIL"),
        None,
    )
    reject_code = (
        rule_code_to_reject_code(first_fail.rule_code).value if first_fail else None
    )
    msg_text = MessageRenderer.render_reject_admin(
        norm_data, filter_result.decision_reason, reject_code=reject_code
    )
    route_to_send = TelegramRoute.ADMIN
```

### Step 6.5: Chạy test

```bash
./.venv/bin/python -m pytest tests/unit/test_message_renderer.py tests/integration/test_api_regressions.py -v
```

### Step 6.6: Commit

```bash
git add app/services/message_renderer.py app/services/webhook_ingestion_service.py tests/unit/test_message_renderer.py
git commit -m "feat(admin-msg): surface reject_code in admin Telegram rejects"
```

---

## Task 7: Reverify Repository + ORM Model

**Mục tiêu:** Bảng `signal_reverify_results` và repository cho reverify endpoint

### Step 7.1: Thêm ORM model

Thêm vào cuối `app/domain/models.py`:

```python
class SignalReverifyResult(Base):
    __tablename__ = "signal_reverify_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_row_id: Mapped[str] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    original_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reverify_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reverify_score: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    reject_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    score_items: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    filter_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
```

**Lưu ý:** Import `JSON` từ `sqlalchemy` đã có ở `models.py:4`.

### Step 7.2: Tạo `app/repositories/reverify_repo.py`

```python
from __future__ import annotations
import uuid
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.domain.models import SignalReverifyResult


class ReverifyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict[str, Any]) -> SignalReverifyResult:
        row = SignalReverifyResult(id=str(uuid.uuid4()), **data)
        self.db.add(row)
        self.db.flush()
        return row

    def list_for_signal(self, signal_row_id: str) -> list[SignalReverifyResult]:
        stmt = (
            select(SignalReverifyResult)
            .where(SignalReverifyResult.signal_row_id == signal_row_id)
            .order_by(SignalReverifyResult.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())
```

### Step 7.3: Apply migration local (dev only)

```bash
PGPASSWORD=postgres psql -h localhost -U postgres -d signal_bot -f migrations/003_v11_upgrade.sql
```

### Step 7.4: Commit

```bash
git add app/domain/models.py app/repositories/reverify_repo.py
git commit -m "feat(reverify): add SignalReverifyResult model + repo"
```

---

## Task 8: Reverify Endpoint

**Mục tiêu:** `POST /api/v1/signals/{signal_id}/reverify` — non-mutating replay

### Step 8.1: Viết integration tests

Tạo `tests/integration/test_reverify_endpoint.py`:

```python
import pytest
from sqlalchemy import select
from app.domain.models import Signal, SignalReverifyResult

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def set_dashboard_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "dashboard_token", "test-dashboard-token")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-dashboard-token"}


def test_reverify_returns_current_rules_result(client, db_session, make_stored_signal):
    signal = make_stored_signal(
        signal_type="SHORT_SQUEEZE",
        strategy="KELTNER_SQUEEZE",
        squeeze_fired=1,
        mom_direction=-1,
        vol_regime="BREAKOUT_IMMINENT",
        rsi=37.5,
        rsi_slope=-5.7,
        kc_position=0.31,
        atr_pct=0.49,
    )

    resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["signal_id"] == signal.signal_id
    assert "reverify_decision" in body
    assert "reverify_score" in body
    assert "reject_code" in body

    # Verify persisted to signal_reverify_results
    rows = db_session.execute(
        select(SignalReverifyResult).where(SignalReverifyResult.signal_row_id == signal.id)
    ).scalars().all()
    assert len(rows) == 1


def test_reverify_unknown_signal_returns_404(client):
    resp = client.post("/api/v1/signals/does-not-exist/reverify", headers=_auth_headers())
    assert resp.status_code == 404


def test_reverify_requires_dashboard_auth(client, make_stored_signal):
    """Reverify là admin operation, phải có dashboard token."""
    signal = make_stored_signal(signal_type="SHORT_SQUEEZE")
    resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify")
    # Không có auth → 401
    assert resp.status_code == 401


def test_reverify_with_valid_auth(client, make_stored_signal):
    """Có dashboard token hợp lệ → 200"""
    signal = make_stored_signal(signal_type="SHORT_SQUEEZE")
    resp = client.post(f"/api/v1/signals/{signal.signal_id}/reverify", headers=_auth_headers())
    assert resp.status_code == 200
```

### Step 8.2: Thêm `make_stored_signal` fixture nếu chưa có

Kiểm tra `tests/integration/conftest.py`. Nếu chưa có `make_stored_signal`, thêm:

```python
@pytest.fixture
def make_stored_signal(db_session):
    created_ids: list = []

    def _mk(**overrides) -> Signal:
        from app.domain.models import Signal, SignalDecision
        import uuid

        sig = Signal(
            id=str(uuid.uuid4()),
            signal_id=f"test-{uuid.uuid4().hex[:8]}",
            source="Bot_Webhook_v84",
            symbol="BTCUSD",
            timeframe="15m",
            side="SHORT",
            price=74988.60,
            entry_price=74988.60,
            stop_loss=75429.33,
            take_profit=73886.79,
            risk_reward=2.5,
            indicator_confidence=0.90,
            raw_payload={
                "secret": "test",
                "signal": "short",
                "symbol": "BTCUSD",
                "timeframe": "15",
                "price": 74988.60,
                "source": "Bot_Webhook_v84",
                "confidence": 0.90,
                "metadata": {
                    "entry": 74988.60,
                    "stop_loss": 75429.33,
                    "take_profit": 73886.79,
                    "signal_type": overrides.get("signal_type", "SHORT_SQUEEZE"),
                    "strategy": overrides.get("strategy", "KELTNER_SQUEEZE"),
                    "squeeze_fired": overrides.get("squeeze_fired", 1),
                    "mom_direction": overrides.get("mom_direction", -1),
                    "vol_regime": overrides.get("vol_regime", "BREAKOUT_IMMINENT"),
                    "rsi": overrides.get("rsi", 37.5),
                    "rsi_slope": overrides.get("rsi_slope", -5.7),
                    "kc_position": overrides.get("kc_position", 0.31),
                    "atr_pct": overrides.get("atr_pct", 0.49),
                    "regime": overrides.get("regime", "WEAK_TREND_DOWN"),
                    "squeeze_bars": overrides.get("squeeze_bars", 6),
                    "stoch_k": overrides.get("stoch_k", 41.4),
                    "atr_percentile": overrides.get("atr_percentile", 78.0),
                    "adx": overrides.get("adx", 17.5),
                    "atr": overrides.get("atr", 367.28),
                    "bar_confirmed": True,
                    "stop_loss": 75429.33,
                    "take_profit": 73886.79,
                },
            },
            **{k: v for k, v in overrides.items() if hasattr(Signal, k)},
        )
        db_session.add(sig)
        db_session.add(SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            decision=overrides.get("original_decision", "PASS_MAIN"),
            decision_reason="seeded",
            telegram_route="MAIN",
        ))
        db_session.commit()
        created_ids.append(sig.id)
        return sig

    yield _mk
```

### Step 8.3: Chạy test → FAIL (endpoint chưa có)

```bash
./.venv/bin/python -m pytest tests/integration/test_reverify_endpoint.py -v
```

### Step 8.4: Implement reverify endpoint

Thêm vào `app/api/signal_controller.py`:

```python
@router.post("/api/v1/signals/{signal_id}/reverify")
def reverify_signal(
    signal_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """Replay filter pipeline với rules hiện tại, không mutate bản ghi gốc."""
    from app.services.filter_engine import FilterEngine
    from app.services.reject_codes import rule_code_to_reject_code
    from app.services.signal_normalizer import SignalNormalizer
    from app.domain.schemas import TradingViewWebhookPayload
    from app.repositories.reverify_repo import ReverifyRepository
    from app.repositories.signal_repo import SignalRepository
    from app.repositories.config_repo import ConfigRepository
    from app.repositories.market_event_repo import MarketEventRepository
    from app.repositories.decision_repo import DecisionRepository

    # 1. Tìm signal gốc
    signal_repo = SignalRepository(db)
    signal = signal_repo.find_by_signal_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="signal not found")

    # 2. Lấy original decision (dùng existing method)
    decision_repo = DecisionRepository(db)
    original = decision_repo.find_by_signal_row_id(signal.id)
    original_decision = original.decision if original else "UNKNOWN"

    # 3. Parse raw_payload và normalize lại
    raw_payload_dict = signal.raw_payload
    payload = TradingViewWebhookPayload.model_validate(raw_payload_dict)
    # Lưu ý: normalize nhận (webhook_event_id, payload) — webhook_event_id=None cho reverify
    norm = SignalNormalizer.normalize(signal.webhook_event_id or "reverify", payload)

    # 4. Chạy filter engine với config hiện tại
    config = ConfigRepository(db).get_signal_bot_config()
    engine = FilterEngine(config, signal_repo, MarketEventRepository(db))
    result = engine.run(norm)

    # 5. Extract reject_code từ first FAIL
    first_fail = next(
        (r for r in result.filter_results if r.result.value == "FAIL"),
        None,
    )
    reject_code = (
        rule_code_to_reject_code(first_fail.rule_code).value if first_fail else None
    )

    # 6. Extract backend score từ BACKEND_SCORE_THRESHOLD rule
    score_item = next(
        (r for r in result.filter_results if r.rule_code == "BACKEND_SCORE_THRESHOLD"),
        None,
    )
    score_value: float | None = None
    score_items: list | None = None
    if score_item and score_item.details:
        score_value = score_item.details.get("score")
        score_items = score_item.details.get("items")

    # 7. Persist reverify result (non-mutating)
    ReverifyRepository(db).create({
        "signal_row_id": signal.id,
        "original_decision": original_decision,
        "reverify_decision": result.final_decision.value,
        "reverify_score": score_value,
        "reject_code": reject_code,
        "decision_reason": result.decision_reason,
        "score_items": score_items,
        "filter_results": [r.to_dict() for r in result.filter_results],
    })
    db.commit()

    return {
        "signal_id": signal_id,
        "original_decision": original_decision,
        "reverify_decision": result.final_decision.value,
        "reverify_score": score_value,
        "reject_code": reject_code,
        "decision_reason": result.decision_reason,
    }
```

**Lưu ý quan trọng:**
- Route: `@router.post("/api/v1/signals/{signal_id}/reverify")` — có prefix `/api/v1`
- Auth: `_auth: None = Depends(require_dashboard_auth)` — bắt buộc dashboard token
- Dùng `DecisionRepository.find_by_signal_row_id()` — KHÔNG phải `find_for_signal()`
- `SignalNormalizer.normalize(webhook_event_id, payload)` — 2 tham số, webhook_event_id có thể là None cho reverify

### Step 8.5: Chạy integration tests

```bash
./.venv/bin/python -m pytest tests/integration/test_reverify_endpoint.py -v
```

### Step 8.6: Commit

```bash
git add app/api/signal_controller.py tests/integration/test_reverify_endpoint.py tests/integration/conftest.py
git commit -m "feat(reverify): POST /api/v1/signals/{id}/reverify endpoint with dashboard auth"
```

---

## Task 9: Analytics — Reject Stats with group_by

**Mục tiêu:** `GET /api/v1/analytics/reject-stats` với group_by `signal_type` + `reject_code`

### Step 9.1: Viết integration tests

Tạo `tests/integration/test_analytics_v11.py`:

```python
import pytest
from sqlalchemy import update

pytestmark = pytest.mark.integration


def test_reject_stats_groups_by_signal_type_and_code(client, db_session, make_stored_signal):
    # Seed 2 SHORT_SQUEEZE rejects (SQ_NO_FIRED) + 1 LONG_V73 reject (BACKEND_SCORE_TOO_LOW)
    for _ in range(2):
        sig = make_stored_signal(signal_type="SHORT_SQUEEZE")
        _seed_reject(db_session, sig, "SQ_NO_FIRED")

    sig = make_stored_signal(signal_type="LONG_V73")
    _seed_reject(db_session, sig, "BACKEND_SCORE_THRESHOLD")

    resp = client.get("/api/v1/analytics/reject-stats?group_by=signal_type,reject_code")
    assert resp.status_code == 200
    body = resp.json()
    buckets = {(b["signal_type"], b["reject_code"]): b["count"] for b in body["buckets"]}
    assert buckets[("SHORT_SQUEEZE", "SQ_NO_FIRED")] == 2
    assert buckets[("LONG_V73", "BACKEND_SCORE_TOO_LOW")] == 1


def test_reject_stats_counts_one_primary_reject_per_signal(client, db_session, make_stored_signal):
    """Một signal có nhiều FAIL vẫn chỉ tính 1 reject bucket chính."""
    sig = make_stored_signal(signal_type="SHORT_SQUEEZE")
    _seed_reject(db_session, sig, "SQ_NO_FIRED")
    _seed_fail_rule(db_session, sig, "SQ_BAD_VOL_REGIME")

    resp = client.get("/api/v1/analytics/reject-stats?group_by=signal_type,reject_code")
    assert resp.status_code == 200
    body = resp.json()
    buckets = {(b["signal_type"], b["reject_code"]): b["count"] for b in body["buckets"]}
    assert buckets[("SHORT_SQUEEZE", "SQ_NO_FIRED")] == 1
    assert ("SHORT_SQUEEZE", "SQ_BAD_VOL_REGIME") not in buckets


def _seed_reject(db_session, sig, rule_code):
    from app.domain.models import SignalDecision, SignalFilterResult
    import uuid
    db_session.execute(
        update(SignalDecision)
        .where(SignalDecision.signal_row_id == sig.id)
        .values(decision="REJECT", decision_reason=rule_code)
    )
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code=rule_code,
        rule_group="test",
        result="FAIL",
        severity="HIGH",
        score_delta=0.0,
        details={"reject_code": rule_code},
    ))
    db_session.commit()


def _seed_fail_rule(db_session, sig, rule_code):
    from app.domain.models import SignalFilterResult
    import uuid
    db_session.add(SignalFilterResult(
        id=str(uuid.uuid4()),
        signal_row_id=sig.id,
        rule_code=rule_code,
        rule_group="test",
        result="FAIL",
        severity="HIGH",
        score_delta=0.0,
        details={"reject_code": rule_code},
    ))
    db_session.commit()
```

### Step 9.2: Chạy test → FAIL (endpoint chưa có)

```bash
./.venv/bin/python -m pytest tests/integration/test_analytics_v11.py -v
```

### Step 9.3: Implement endpoint

Thêm vào `app/api/analytics_controller.py`:

```python
@router.get("/reject-stats")
def reject_stats(
    group_by: str = Query(default=""),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Reject analytics với optional group_by.
    group_by=signal_type,reject_code → group by both dimensions.
    """
    from sqlalchemy import select, func
    from app.domain.models import Signal, SignalDecision, SignalFilterResult

    if "signal_type" in group_by and "reject_code" in group_by:
        # Mỗi rejected signal chỉ được count 1 primary FAIL để tránh inflate analytics.
        from app.services.reject_codes import rule_code_to_reject_code

        stmt = (
            select(
                Signal.id,
                Signal.signal_type,
                SignalFilterResult.rule_code,
                SignalFilterResult.created_at,
            )
            .join(SignalDecision, SignalDecision.signal_row_id == Signal.id)
            .join(
                SignalFilterResult,
                SignalFilterResult.signal_row_id == Signal.id,
            )
            .where(
                SignalDecision.decision == "REJECT",
                SignalFilterResult.result == "FAIL",
            )
            .order_by(
                Signal.id,
                SignalFilterResult.created_at.asc(),
                SignalFilterResult.id.asc(),
            )
        )

        rows = db.execute(stmt).all()
        primary_fail_by_signal: dict[str, tuple[str | None, str]] = {}
        for signal_row_id, signal_type, rule_code, _created_at in rows:
            if signal_row_id not in primary_fail_by_signal:
                primary_fail_by_signal[signal_row_id] = (signal_type, rule_code)

        counts: dict[tuple[str, str], int] = {}
        for signal_type, rule_code in primary_fail_by_signal.values():
            reject_code = rule_code_to_reject_code(rule_code).value
            key = (signal_type or "UNKNOWN", reject_code)
            counts[key] = counts.get(key, 0) + 1

        return {
            "buckets": [
                {"signal_type": st, "reject_code": rc, "count": c}
                for (st, rc), c in sorted(counts.items())
            ]
        }

    # Fallback: reject stats đơn giản (tổng số reject)
    stmt = (
        select(func.count(SignalDecision.id))
        .where(SignalDecision.decision == "REJECT")
    )
    total_rejects = db.execute(stmt).scalar_one()
    return {"total_rejects": total_rejects, "buckets": []}
```

**Lưu ý:** Dùng SQLAlchemy 2.0 `select()` — KHÔNG dùng `db.query()`. Reject-stats phải đếm theo primary reject mỗi signal, không đếm theo tổng số `SignalFilterResult.result == "FAIL"` vì một rejected signal có thể có nhiều FAIL.

### Step 9.4: Chạy tests

```bash
./.venv/bin/python -m pytest tests/integration/test_analytics_v11.py tests/integration/test_analytics.py -v
```

### Step 9.5: Commit

```bash
git add app/api/analytics_controller.py tests/integration/test_analytics_v11.py
git commit -m "feat(analytics): add reject-stats with group_by signal_type + reject_code"
```

---

## Task 10: E2E Pipeline Tests + Sample Fixtures

**Mục tiêu:** 3 E2E fixtures cho regression testing

### Step 10.1: Tạo fixture payloads

Tạo thư mục `docs/examples/v11_sample_payloads/`:

**`short_squeeze_pass.json`:**
```json
{
  "secret": "element-camera-fan",
  "signal": "short",
  "symbol": "BTCUSD",
  "timeframe": "15",
  "price": 74988.60,
  "source": "Bot_Webhook_v84",
  "confidence": 0.90,
  "metadata": {
    "entry": 74988.60,
    "stop_loss": 75429.33,
    "take_profit": 73886.79,
    "atr": 367.28,
    "atr_pct": 0.49,
    "adx": 17.5,
    "rsi": 37.5,
    "rsi_slope": -5.7,
    "stoch_k": 41.4,
    "macd_hist": -12.3,
    "signal_type": "SHORT_SQUEEZE",
    "strategy": "KELTNER_SQUEEZE",
    "regime": "WEAK_TREND_DOWN",
    "vol_regime": "BREAKOUT_IMMINENT",
    "squeeze_on": 0,
    "squeeze_bars": 6,
    "squeeze_fired": 1,
    "mom_direction": -1,
    "kc_position": 0.31,
    "atr_percentile": 78.0
  }
}
```

**`short_squeeze_fail_not_fired.json`:** Copy `short_squeeze_pass.json`, đổi `"squeeze_fired": 0`.

**`long_v73_pass.json`:**
```json
{
  "secret": "element-camera-fan",
  "signal": "long",
  "symbol": "BTCUSD",
  "timeframe": "15",
  "price": 70000.00,
  "source": "Bot_Webhook_v84",
  "confidence": 0.92,
  "metadata": {
    "entry": 70000.00,
    "stop_loss": 69580.00,
    "take_profit": 70701.4,
    "atr_pct": 0.35,
    "rsi": 24.0,
    "rsi_slope": 3.0,
    "stoch_k": 8.0,
    "signal_type": "LONG_V73",
    "strategy": "RSI_STOCH_V73",
    "regime": "WEAK_TREND_UP",
    "vol_regime": "TRENDING_LOW_VOL"
  }
}
```
RR = (70701.4 - 70000) / (70000 - 69580) = 701.4 / 420 ≈ 1.67 (trong ±10% của target 1.67 ✅)

### Step 10.2: Viết E2E tests

Tạo `tests/integration/test_v11_pipeline.py`:

```python
import json
from pathlib import Path
import pytest

pytestmark = pytest.mark.integration

FIXTURES = Path("docs/examples/v11_sample_payloads")


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_short_squeeze_pass_end_to_end(client, db_session):
    resp = client.post("/api/v1/webhooks/tradingview", json=_load("short_squeeze_pass.json"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] in ("PASS_MAIN", "PASS_WARNING")


def test_short_squeeze_fail_not_fired(client, db_session):
    resp = client.post(
        "/api/v1/webhooks/tradingview",
        json=_load("short_squeeze_fail_not_fired.json"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "REJECT"


def test_long_v73_pass(client, db_session):
    resp = client.post("/api/v1/webhooks/tradingview", json=_load("long_v73_pass.json"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] in ("PASS_MAIN", "PASS_WARNING")
```

### Step 10.3: Chạy E2E tests

```bash
./.venv/bin/python -m pytest tests/integration/test_v11_pipeline.py -v
```

### Step 10.4: Chạy full regression suite

```bash
./.venv/bin/python -m pytest -q
```

### Step 10.5: Commit

```bash
git add docs/examples/v11_sample_payloads tests/integration/test_v11_pipeline.py
git commit -m "test(v11): add E2E pipeline coverage with 3 sample payloads"
```

---

## Task 11: Docs Update

**Mục tiêu:** Cập nhật tài liệu V1.1

### Step 11.1: Cập nhật `docs/FILTER_RULES.md`

Thêm section mới "## V1.1 Strategy-Specific Rules" sau section hiện có:

```
## V1.1 Strategy-Specific Rules

### Phase 2.5 — Strategy Validation

#### SHORT_SQUEEZE

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `SQ_NO_FIRED` | HIGH | FAIL | REJECT |
| `SQ_BAD_MOM_DIRECTION` | HIGH | FAIL | REJECT |
| `SQ_BAD_VOL_REGIME` | HIGH | FAIL | REJECT |
| `SQ_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `SQ_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `SQ_KC_POSITION_FLOOR` | MEDIUM | WARN | → PASS_WARNING |

#### SHORT_V73

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `S_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `S_BASE_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `S_BASE_STOCH_FLOOR` | MEDIUM | WARN | → PASS_WARNING |

#### LONG_V73

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `L_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `L_BASE_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `L_BASE_STOCH_FLOOR` | MEDIUM | WARN | → PASS_WARNING |

### Phase 3c — Rescoring + Profile Match

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `RR_PROFILE_MATCH` (out of band) | MEDIUM | WARN | → PASS_WARNING |
| `BACKEND_SCORE_THRESHOLD` (score < 75) | MEDIUM | WARN | → PASS_WARNING |
```

### Step 11.2: Cập nhật `docs/FILTER_RULES.md` — sửa typo

Sửa `docs/FILTER_RULES.md:459`:
```
- "duplicate_price_tolerance_pct": 0.2,  ← SAI
+ "duplicate_price_tolerance_pct": 0.002,  ← ĐÚNG (0.2%)
```

### Step 11.3: Tạo `docs/CHANGELOG_V1.1.md`

```markdown
# V1.1 Changelog

Released: 2026-04-25

## Added
- Strategy-specific validation (SHORT_SQUEEZE, SHORT_V73, LONG_V73).
- Backend rescoring engine with config-driven bonus/penalty table.
- `RR_PROFILE_MATCH` rule for target-band RR validation (±10%).
- Reject code taxonomy (`app/services/reject_codes.py`).
- `POST /api/v1/signals/{id}/reverify` endpoint + `signal_reverify_results` table.
- `GET /api/v1/analytics/reject-stats?group_by=signal_type,reject_code` aggregation.
- Admin reject Telegram messages now include `RejectCode:` line.

## Changed
- `MIN_RR_REQUIRED` giữ nguyên lower-bound check (KHÔNG đổi).
- `RR_PROFILE_MATCH` dùng WARN (pilot) thay vì FAIL.
- `BACKEND_SCORE_THRESHOLD` dùng WARN MEDIUM (pilot) thay vì FAIL — giữ boolean-gate routing.
- `FilterEngine.run()` adds Phase 2.5 (strategy validation) và Phase 3c (rescoring + profile match).
- Default `score_pass_threshold = 75` (pilot-loose; tighten via system_configs without redeploy).

## Unchanged / Deferred (deliberately not in v1.1)
- SOFT_PASS decision type.
- Position-state risk gate.
- User profile aggressive/conservative mode.
- Cooldown-as-reject (still WARN-only).
```

### Step 11.4: Commit

```bash
git add docs/FILTER_RULES.md docs/CHANGELOG_V1.1.md
git commit -m "docs: v1.1 upgrade — strategy rules, reject codes, changelog"
```

---

## Regression Baseline

Trước khi bắt đầu, DEV nên record số tests hiện tại:

```bash
./.venv/bin/python -m pytest --co -q 2>/dev/null | wc -l
```

Mong đợi: ~100 tests. Sau V1.1: ~130+ tests (thêm ~30 tests mới).

---

## Acceptance Criteria

| # | Criteria | Verify |
|---|---|---|
| AC-1 | Happy path SHORT_SQUEEZE → PASS_MAIN/PASS_WARNING | `test_short_squeeze_pass_end_to_end` |
| AC-2 | SHORT_SQUEEZE + squeeze_fired=0 → REJECT | `test_short_squeeze_fail_not_fired` |
| AC-3 | Backend score < threshold → WARN (pilot) | `test_backend_score_threshold_warns_when_low` |
| AC-4 | RR out of band → WARN (pilot) | `test_rr_profile_match_warns_on_upper_bound` |
| AC-5 | Reverify endpoint hoạt động + persisted | `test_reverify_returns_current_rules_result` |
| AC-6 | Reverify requires dashboard auth | `test_reverify_requires_dashboard_auth` |
| AC-7 | Reject stats group_by hoạt động | `test_reject_stats_groups_by_signal_type_and_code` |
| AC-8 | Admin message có reject_code | `test_render_reject_admin_includes_reject_code` |
| AC-9 | Existing V1.0 tests không regression | `./.venv/bin/python -m pytest tests/unit tests/integration/test_api_regressions.py -v` |
| AC-10 | Migration idempotent | Chạy lại `003_v11_upgrade.sql` — không error |

---

## Rollout Checklist

```
[ ] Chạy migration 002 trên production DB
[ ] Verify DB config có strategy_thresholds + rescoring keys
[ ] Verify new reject codes hiển thị đúng trong admin Telegram
[ ] Monitor reject-stats sau 1 tuần
[ ] Sau 2 tuần: review score distribution → quyết định có tăng threshold không
[ ] Sau 2 tuần: review RR_PROFILE_MATCH → quyết định có đổi WARN → FAIL không
```
