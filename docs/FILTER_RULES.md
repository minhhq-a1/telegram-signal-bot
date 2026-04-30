# Filter Rules — Signal Bot V1.1
<!-- Cập nhật: Thay server_score continuous thành boolean gate system -->
<!-- Lý do: server_score = heuristic + heuristic không có predictive value thực -->

## Mục tiêu

Layer 2 filtering có nhiệm vụ:
- Giảm noise và spam
- Chặn tín hiệu kỹ thuật rõ ràng sai
- Chuẩn bị đủ audit trail để đánh giá sau 2–4 tuần paper trading
- **Không** pretend có khả năng predict win rate

## Nguyên tắc thiết kế (quan trọng)

Layer 2 được thiết kế như **bộ lọc boolean**, không phải scoring system:

- Mỗi rule hoặc **PASS** hoặc **FAIL** hoặc **WARN**
- **FAIL** = reject cứng, không qua
- **WARN** = có cảnh báo, vẫn qua nhưng route sang kênh warning
- Không có continuous score quyết định pass/reject — xem section 5

**Lý do bỏ server_score làm threshold:**
`indicator_confidence` là heuristic hardcode trong Pine Script. Cộng thêm score_delta tùy ý
(−0.08, +0.03...) không có statistical basis vào một con số vốn đã không có ground truth
→ kết quả không đáng tin hơn, chỉ phức tạp hơn.

`server_score` vẫn được tính và lưu DB để **phân tích sau** — nhưng không dùng làm threshold pass/reject.

---

## 1. Thứ tự xử lý

```
Phase 1: Hard Validation   ← Short-circuit: bất kỳ FAIL → REJECT ngay
Phase 2: Trade Math        ← RR calculation + direction sanity
Phase 3: Business Rules    ← Boolean gates: PASS / WARN / FAIL
Phase 4: Routing           ← Dựa trên FAIL/WARN count, không dựa trên score
```

---

## 2. Phase 1 — Hard Validation

### AUTH_SECRET_VALID
```
Rule:     secrets.compare_digest(payload.secret, env.TRADINGVIEW_SHARED_SECRET)
Severity: CRITICAL
On FAIL:  REJECT — return 401
```

### PAYLOAD_JSON_VALID
```
Rule:     Body parseable as valid JSON
Severity: CRITICAL
On FAIL:  REJECT — return 400 INVALID_JSON
```

### PAYLOAD_SCHEMA_VALID
```
Rule:     Tất cả required fields có mặt và đúng type
Severity: CRITICAL
On FAIL:  REJECT — return 400 INVALID_SCHEMA
```

### SIGNAL_SIDE_VALID
```
Rule:     signal ∈ {"long", "short"}
Severity: CRITICAL
On FAIL:  REJECT
```

### SYMBOL_ALLOWED
```
Rule:     symbol ∈ config.allowed_symbols
          Default: ["BTCUSDT", "BTCUSD"]
Severity: CRITICAL
On FAIL:  REJECT — return 400 UNSUPPORTED_SYMBOL
```

### TIMEFRAME_ALLOWED
```
Rule:     timeframe ∈ config.allowed_timeframes
          V1.1 whitelist: ["1m", "3m", "5m", "12m", "15m", "30m", "1h"]
          Rejected: 30S, 45S, 2m, 4m, 6m–11m, 13m–20m, 4h, 1d
Severity: CRITICAL
On FAIL:  REJECT (runtime response currently `200` with `decision="REJECT"` via filter/persist flow)
Lý do:   TF quá thấp → nhiều noise; 4m → thiếu dữ liệu train; TF lẻ → khó vận hành
```

### CONFIDENCE_RANGE_VALID
```
Rule:     0.0 <= confidence <= 1.0
Severity: HIGH
On FAIL:  REJECT
```

### PRICE_VALID
```
Rule:     price > 0 AND entry > 0 AND stop_loss > 0 AND take_profit > 0
Severity: HIGH
On FAIL:  REJECT
```

---

## 3. Phase 2 — Trade Math

### DIRECTION_SANITY_VALID
```
LONG:   stop_loss < entry AND entry < take_profit
SHORT:  take_profit < entry AND entry < stop_loss

Severity: CRITICAL
On FAIL:  REJECT — return 400 INVALID_SIGNAL_VALUES
Lý do:   Kiểm tra toán học thuần túy. Nếu sai → indicator có bug hoặc payload bị corrupt.
```

### RR Calculation
```python
if side == "LONG":
    risk   = entry - stop_loss
    reward = take_profit - entry
else:
    risk   = stop_loss - entry
    reward = entry - take_profit

risk_reward = round(reward / risk, 4) if risk > 0 else None
```

### MIN_RR_REQUIRED
```
Base trades (signal_type != "SHORT_SQUEEZE"):
    rr >= config.rr_min_base     (default: 1.5)

Squeeze trades (signal_type == "SHORT_SQUEEZE"):
    rr >= config.rr_min_squeeze  (default: 2.0)

Severity: HIGH
On FAIL:  REJECT
```

---

## 4. Phase 3 — Business Rules

### MIN_CONFIDENCE_BY_TF
```
Ngưỡng tối thiểu theo timeframe:
    1m:  >= 0.82
    3m:  >= 0.80
    5m:  >= 0.78
    12m: >= 0.76
    15m: >= 0.74
    30m: >= 0.72
    1h:  >= 0.70

Severity: HIGH
On FAIL:  REJECT

⚠️ Giới hạn đã biết:
   Ngưỡng derive từ ~136 signals — sample nhỏ, nguy cơ overfit cao.
   Review và điều chỉnh sau 4 tuần paper trading dựa trên outcome thực tế.
   Coi đây là starting point, không phải optimal threshold.
```

### REGIME_HARD_BLOCK
```
LONG  + regime == "STRONG_TREND_DOWN"  → FAIL → REJECT
SHORT + regime == "STRONG_TREND_UP"    → FAIL → REJECT

Severity: HIGH
On FAIL:  REJECT

⚠️ Giới hạn đã biết:
   regime lấy từ payload indicator — circular dependency.
   Nếu indicator tính sai regime, rule này cũng fail theo.
   V1.1+: thay bằng independent regime check từ exchange API.
```

### VOLATILITY_WARNING
```
vol_regime == "RANGING_HIGH_VOL":
    result:   WARN
    severity: MEDIUM
    → Route sang WARNING channel

vol_regime == "SQUEEZE_BUILDING":
    result:   WARN
    severity: LOW
    → Route sang WARNING channel (nếu không có WARN MEDIUM+ nào khác: vẫn MAIN)

vol_regime == "TRENDING_HIGH_VOL":
    result:   PASS
    severity: INFO

⚠️ Giới hạn đã biết:
   vol_regime từ payload — cùng circular dependency.
   Dùng như tín hiệu advisory, không phải hard filter.
```

### LOW_VOLUME_WARNING
```
vol_ratio < 0.8:
    result:   WARN
    severity: MEDIUM
    → Route sang WARNING channel

0.8 <= vol_ratio < 1.0:
    result:   WARN
    severity: LOW

vol_ratio >= 1.0 hoặc vol_ratio is None:
    result:   PASS
```

### DUPLICATE_SUPPRESSION
```
REJECT nếu tồn tại signal trong DB cùng:
    symbol + timeframe + side + signal_type
    trong vòng cooldown_minutes
    VÀ |new_entry - existing_entry| / existing_entry < 0.002 (0.2%)

Cooldown windows:
    1m:  5 phút
    3m:  8 phút
    5m:  10 phút
    12m: 20 phút
    15m: 25 phút
    30m: 45 phút
    1h:  90 phút

Severity: HIGH
On FAIL:  REJECT
Lý do:   Giải quyết vấn đề kỹ thuật thực tế — TradingView resend, indicator fire nhiều lần.
         Đây là rule đáng tin cậy nhất vì không phụ thuộc market prediction.
```

### COOLDOWN_ACTIVE
```
Nếu đã có PASS_MAIN cùng symbol + timeframe + side trong cooldown window
(nhưng entry price khác — không phải duplicate):
    result:   WARN
    severity: MEDIUM
    → Route sang WARNING channel

Khác với DUPLICATE_SUPPRESSION:
    Duplicate:  entry gần giống → reject cứng (likely same signal resent)
    Cooldown:   entry khác nhưng cùng side gần đây → warning (có thể signal mới hợp lệ)
```

### HTF_BIAS_CHECK
```
V1.1 — DISABLED hoàn toàn (ENABLE_HTF_FILTER=false):
    Không implement fallback dùng regime từ payload.
    Regime từ payload = circular dependency với REGIME_HARD_BLOCK.
    Thà không có rule còn hơn có rule không độc lập.

Future — Khi có independent market data:
    TF 1m, 3m, 5m: fetch EMA200 15m từ exchange API
    LONG  WARN nếu price < EMA200_15m
    SHORT WARN nếu price > EMA200_15m
```

### NEWS_BLOCK
```
Config: enable_news_block=true

Query bảng market_events hiện tại:
    WHERE impact = 'HIGH'
    AND start_time <= :signal_time + interval '15 minutes'
    AND end_time >= :signal_time - interval '30 minutes'

Nếu có event active:
    result:   FAIL
    severity: HIGH
    On FAIL:  REJECT

Events nhập tay: CPI, FOMC, PCE, NFP, BTC ETF events lớn

⚠️ Giới hạn: Dễ miss nếu quên nhập. Cần reminder thủ công trước mỗi sự kiện lớn.
```

---

## 5. Phase 4 — Routing (thay thế Scoring)

### Decision logic

```python
def _decide(self, results: list[FilterResult]) -> tuple[DecisionType, TelegramRoute]:
    # Bất kỳ FAIL nào → REJECT
    if any(r.result == RuleResult.FAIL for r in results):
        return DecisionType.REJECT, TelegramRoute.NONE

    # Có WARN severity MEDIUM trở lên → WARNING channel
    significant_warns = [
        r for r in results
        if r.result == RuleResult.WARN
        and r.severity in (RuleSeverity.MEDIUM, RuleSeverity.HIGH)
    ]
    if significant_warns:
        return DecisionType.PASS_WARNING, TelegramRoute.WARN

    # WARN LOW hoặc không có WARN → MAIN channel
    return DecisionType.PASS_MAIN, TelegramRoute.MAIN
```

### Decision Matrix

| Trạng thái rules | Decision | Route |
|---|---|---|
| Không có FAIL, không có WARN | PASS_MAIN | MAIN |
| Không có FAIL, chỉ WARN LOW | PASS_MAIN | MAIN |
| Không có FAIL, có ≥1 WARN MEDIUM+ | PASS_WARNING | WARN |
| Có bất kỳ FAIL nào | REJECT | NONE |

### server_score — chỉ để analytics, không dùng để route

```python
# Tính để lưu DB và phân tích sau paper trading
server_score = indicator_confidence + sum(r.score_delta for r in results)
server_score = max(0.0, min(1.0, server_score))
# Lưu vào signals.server_score
# KHÔNG dùng trong routing decision
```

### Score delta reference (analytics only)

| Điều kiện | Delta | Độ tin cậy |
|---|---|---|
| `vol_regime == RANGING_HIGH_VOL` | −0.08 | Thấp — heuristic |
| `vol_regime == SQUEEZE_BUILDING` | −0.03 | Thấp — heuristic |
| `vol_regime == TRENDING_HIGH_VOL` | +0.03 | Thấp — heuristic |
| Cooldown active | −0.10 | Trung bình |
| Low volume (vol_ratio < 0.8) | −0.05 | Trung bình |

---

## 6. Pseudocode filter_engine.run()

```python
def run(self, signal: dict) -> FilterExecutionResult:
    results: list[FilterResult] = []

    # Phase 1: Hard validation
    self._check_symbol(signal, results)
    self._check_timeframe(signal, results)
    self._check_confidence_range(signal, results)
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

def _build_result(self, results, signal, reason) -> FilterExecutionResult:
    # server_score: tính để log, không để route
    score = signal["indicator_confidence"]
    for r in results:
        score += r.score_delta
    score = max(0.0, min(1.0, score))

    decision, route = self._decide(results)
    return FilterExecutionResult(
        filter_results=results,
        server_score=round(score, 4),
        final_decision=decision.value,
        decision_reason=reason,
        route=route.value,
    )

def _has_fail(self, results: list[FilterResult]) -> bool:
    return any(r.result == RuleResult.FAIL for r in results)
```

---

## 7. Rule Code Catalog

### Validation group
```
AUTH_SECRET_VALID
PAYLOAD_JSON_VALID
PAYLOAD_SCHEMA_VALID
SIGNAL_SIDE_VALID
SYMBOL_ALLOWED
TIMEFRAME_ALLOWED
CONFIDENCE_RANGE_VALID
PRICE_VALID
DIRECTION_SANITY_VALID
```

### Trading group
```
MIN_CONFIDENCE_BY_TF
MIN_RR_REQUIRED
REGIME_HARD_BLOCK
VOLATILITY_WARNING
LOW_VOLUME_WARNING
NEWS_BLOCK
DUPLICATE_SUPPRESSION
COOLDOWN_ACTIVE
HTF_BIAS_CHECK        ← disabled, placeholder cho future independent market data
```

### Routing group
```
ROUTE_MAIN
ROUTE_WARNING
ROUTE_REJECT
```

---

## 8. Config runtime (DB: `system_configs`)

```json
{
  "allowed_symbols": ["BTCUSDT", "BTCUSD"],
  "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
  "confidence_thresholds": {
    "1m": 0.82,
    "3m": 0.80,
    "5m": 0.78,
    "12m": 0.76,
    "15m": 0.74,
    "30m": 0.72,
    "1h": 0.70
  },
  "cooldown_minutes": {
    "1m": 5,
    "3m": 8,
    "5m": 10,
    "12m": 20,
    "15m": 25,
    "30m": 45,
    "1h": 90
  },
  "rr_min_base": 1.5,
  "rr_min_squeeze": 2.0,
  "duplicate_price_tolerance_pct": 0.002,
  "news_block_before_min": 15,
  "news_block_after_min": 30,
  "log_reject_to_admin": true
}
```

**Đã bỏ:** `main_score_threshold`, `warning_score_threshold` — không còn dùng score để route.

---

## 9. V1.1 — Strategy-Specific Rules (Pilot Mode)

### 9.1 — Routing Policy

**Boolean gate vẫn giữ nguyên.** `server_score` chỉ dùng cho analytics, không dùng để route. `BACKEND_SCORE_THRESHOLD` trong pilot mode trả về WARN, không FAIL.

### 9.2 — Phase 2.5: Strategy Validation (sau Phase 2 Trade Math)

**Pilot rule severity policy:**
- `HIGH` severity → `FAIL` → REJECT
- `MEDIUM` severity → `WARN` → PASS_WARNING
- `INFO` severity → `PASS` → không ảnh hưởng route

#### SHORT_SQUEEZE — Phase 2.5

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `SQ_NO_FIRED` | HIGH | FAIL | REJECT |
| `SQ_BAD_MOM_DIRECTION` | HIGH | FAIL | REJECT |
| `SQ_BAD_VOL_REGIME` | HIGH | FAIL | REJECT |
| `SQ_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `SQ_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `SQ_KC_POSITION_FLOOR` | MEDIUM | WARN | → PASS_WARNING |

**Logic chi tiết:**
- `SQ_NO_FIRED`: `squeeze_fired in (0, False)` → FAIL
- `SQ_BAD_MOM_DIRECTION`: `mom_direction != -1` → FAIL (Pine gửi int -1/0/1)
- `SQ_BAD_VOL_REGIME`: `vol_regime != "BREAKOUT_IMMINENT"` → FAIL
- `SQ_BAD_STRATEGY_NAME`: `strategy != "KELTNER_SQUEEZE"` → FAIL
- `SQ_RSI_FLOOR`: `rsi < rsi_min (35)` → WARN
- `SQ_KC_POSITION_FLOOR`: `kc_position > kc_position_max (0.55)` → WARN

#### SHORT_V73 — Phase 2.5

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `S_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `S_BASE_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `S_BASE_STOCH_FLOOR` | MEDIUM | WARN | → PASS_WARNING |

**Logic chi tiết:**
- `S_BASE_BAD_STRATEGY_NAME`: `strategy != "RSI_STOCH_V73"` → FAIL
- `S_BASE_RSI_FLOOR`: `rsi < rsi_min (60)` → WARN
- `S_BASE_STOCH_FLOOR`: `stoch_k < stoch_k_min (70)` → WARN

#### LONG_V73 — Phase 2.5

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `L_BASE_BAD_STRATEGY_NAME` | HIGH | FAIL | REJECT |
| `L_BASE_RSI_FLOOR` | MEDIUM | WARN | → PASS_WARNING |
| `L_BASE_STOCH_FLOOR` | MEDIUM | WARN | → PASS_WARNING |

**Logic chi tiết:**
- `L_BASE_BAD_STRATEGY_NAME`: `strategy != "RSI_STOCH_V73"` → FAIL
- `L_BASE_RSI_FLOOR`: `rsi > rsi_max (35)` → WARN
- `L_BASE_STOCH_FLOOR`: `stoch_k > stoch_k_max (20)` → WARN

### 9.3 — Phase 3c: RR Profile Match (sau Advisory Warnings)

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `RR_PROFILE_MATCH` (out of band) | MEDIUM | WARN | → PASS_WARNING |

- `target ± 10%` cho mỗi signal_type
- `MIN_RR_REQUIRED` (lower-bound) vẫn giữ nguyên, không đổi

### 9.4 — Phase 3d: Backend Rescoring (cuối Phase 3)

| Rule | Severity | Result | Pilot Action |
|---|---|---|---|
| `BACKEND_SCORE_THRESHOLD` (score < 75) | MEDIUM | WARN | → PASS_WARNING |

- Config: `score_pass_threshold = 75`
- Scoring: config-driven bonus/penalty table, clamp [0, 100]
- Pilot mode: score < threshold → WARN, không FAIL

**Score example (SHORT_SQUEEZE ideal):**
```
base=70 + vol_regime_breakout_imminent+8 + regime_weak_trend_down+6
+ mom_direction_neg1+5 + squeeze_bars_ge_6+5 + rsi_slope_le_neg4+4
+ atr_percentile_ge_70+3 + kc_position_le_040+3 + confidence_ge_090+3
= 110 → clamp 100
```

### 9.5 — V1.1 Config Defaults

```json
{
  "rr_tolerance_pct": 0.10,
  "rr_target_by_type": {
    "SHORT_SQUEEZE": 2.5,
    "SHORT_V73": 1.67,
    "LONG_V73": 1.67
  },
  "score_pass_threshold": 75,
  "strategy_thresholds": {
    "SHORT_SQUEEZE": {
      "rsi_min": 35,
      "kc_position_max": 0.55
    }
  },
  "rescoring": {
    "SHORT_SQUEEZE": {
      "base": 70,
      "bonuses": {
        "vol_regime_breakout_imminent": 8,
        "regime_weak_trend_down": 6
      },
      "penalties": {
        "regime_strong_trend_up": -15,
        "rsi_lt_35": -8
      }
    }
  }
}
```

### 9.6 — V1.1 New Reject Codes

| RejectCode | Mapped từ |
|---|---|
| `SQ_NO_FIRED` | `SQ_NO_FIRED` FAIL |
| `SQ_BAD_MOM_DIRECTION` | `SQ_BAD_MOM_DIRECTION` FAIL |
| `SQ_BAD_VOL_REGIME` | `SQ_BAD_VOL_REGIME` FAIL |
| `SQ_BAD_STRATEGY_NAME` | `SQ_BAD_STRATEGY_NAME` FAIL |
| `SQ_RSI_TOO_LOW` | `SQ_RSI_FLOOR` WARN |
| `SQ_KC_POSITION_TOO_HIGH` | `SQ_KC_POSITION_FLOOR` WARN |
| `S_BASE_BAD_STRATEGY_NAME` | `S_BASE_BAD_STRATEGY_NAME` FAIL |
| `S_BASE_RSI_TOO_LOW` | `S_BASE_RSI_FLOOR` WARN |
| `S_BASE_STOCH_TOO_LOW` | `S_BASE_STOCH_FLOOR` WARN |
| `L_BASE_BAD_STRATEGY_NAME` | `L_BASE_BAD_STRATEGY_NAME` FAIL |
| `L_BASE_RSI_TOO_HIGH` | `L_BASE_RSI_FLOOR` WARN |
| `L_BASE_STOCH_TOO_HIGH` | `L_BASE_STOCH_FLOOR` WARN |
| `RR_PROFILE_MISMATCH` | `RR_PROFILE_MATCH` WARN |
| `BACKEND_SCORE_TOO_LOW` | `BACKEND_SCORE_THRESHOLD` WARN |

---

## 10. Rủi ro đã biết

| Rủi ro | Mức độ | Kế hoạch |
|---|---|---|
| Confidence threshold overfit (sample ~136 signals) | CAO | Review sau 4 tuần paper, điều chỉnh theo outcome thực tế |
| Regime circular dependency (data từ indicator) | TRUNG BÌNH | Future: thêm independent market data source |
| News block dễ miss (nhập tay) | TRUNG BÌNH | Đặt reminder lịch trước mỗi sự kiện |
| HTF bias không có ở V1 | THẤP | Disabled hoàn toàn — không dùng fallback giả |
| Vol/regime data từ indicator có thể sai | THẤP | Chỉ dùng làm WARN advisory, không làm hard FAIL |

---

## 10. Kế hoạch cải thiện sau paper trading

Sau 2–4 tuần, dùng data từ `signal_outcomes` để:

1. **Calibrate confidence threshold** — TF nào threshold quá cao/thấp so với win rate thực?
2. **Validate regime rules** — STRONG_TREND_DOWN có thực sự block bad signals không?
3. **Validate vol_regime warnings** — RANGING_HIGH_VOL có correlate với bad outcome không?
4. **Xem cooldown có bỏ sót signal tốt không** — adjust window nếu cần

Chỉ sau bước này mới cân nhắc thêm lại scoring mechanism — với data thực làm basis.
