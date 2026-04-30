# Architecture — Telegram Signal Bot V1.1

## 1. Data Flow tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│  TradingView                                                    │
│  Pine Script v8.4 [BTC]                                        │
│  barstate.isconfirmed → alert() → JSON webhook                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS POST /api/v1/webhooks/tradingview
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  A. Webhook API Layer                                           │
│  ├── Parse JSON                                                │
│  ├── Validate Content-Type                                     │
│  ├── Auth: secret field check trong request body               │
│  ├── Store raw webhook_event (DB)                              │
│  └── Pass to Signal Processor                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  B. Signal Processing Service                                   │
│  ├── Idempotency check (signal_id đã tồn tại?)                │
│  ├── signal_normalizer: map → NormalizedSignal                 │
│  ├── Tính risk/reward                                          │
│  └── Pass to Filter Engine                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  C. Filter Engine (Layer 2)                                     │
│  Phase 1: Hard validation (symbol, TF, direction, confidence)  │
│  Phase 2: Trade math (RR calc, direction sanity)               │
│  Phase 3: Business rules (duplicate, cooldown, regime, news)   │
│  Phase 4: Boolean routing (FAIL/WARN → decision)               │
│  Output: FilterExecutionResult                                  │
│    ├── filter_results[]  (mỗi rule đã chạy)                   │
│    ├── server_score      (float 0–1)                           │
│    ├── final_decision    (PASS_MAIN / PASS_WARNING / REJECT)   │
│    └── route             (MAIN / WARN / NONE)                  │
└──────────┬───────────────────────────────────────┬─────────────┘
           │                                       │
           ▼                                       ▼
┌─────────────────────┐               ┌─────────────────────────┐
│  D. Persistence      │               │  E. Telegram Notifier   │
│  ├── signals         │               │  ├── render message      │
│  ├── filter_results  │               │  ├── select channel      │
│  ├── signal_decision │               │  ├── send (retry x3)     │
│  └── telegram_msgs   │               │  └── log delivery status │
└─────────────────────┘               └─────────────────────────┘
```

---

## 2. Thành phần chi tiết

### A. Webhook API (`app/api/webhook_controller.py`)

**Trách nhiệm:**
- Expose `POST /api/v1/webhooks/tradingview`
- Đọc raw request body, audit vào `webhook_events`, rồi mới parse JSON + validate `TradingViewWebhookPayload`
- Xác thực `secret` (so sánh với `TRADINGVIEW_SHARED_SECRET`)
- Store `webhook_events` raw
- Trả `200 accepted` cho duplicate và các signal đã qua boundary validation
- Trả `400` cho `INVALID_JSON` / `INVALID_SCHEMA`, `401` nếu secret sai

**Quan trọng:** Response phải nhanh. Mọi xử lý nặng (Telegram, DB insert lớn) có thể dùng background task nếu tải tăng.

### B. Signal Normalizer (`app/services/signal_normalizer.py`)

**Trách nhiệm:**
- Map `TradingViewWebhookPayload` → `NormalizedSignal` (internal model)
- Tính `risk_reward`
- Chuẩn hóa `side` về `LONG` / `SHORT` (uppercase)
- Enrich metadata

**Input:** `TradingViewWebhookPayload` (Pydantic)  
**Output:** `dict` / `NormalizedSignal`

### C. Filter Engine (`app/services/filter_engine.py`)

**Core business logic.** Xem chi tiết tại [FILTER_RULES.md](./FILTER_RULES.md).

**Nguyên tắc:**
- Chạy theo thứ tự phase 1 → 4
- Short-circuit: nếu phase 1 fail → không chạy phase 2+
- Mỗi rule trả `FilterResult` (rule_code, result, severity, score_delta)
- Routing: FAIL → REJECT | WARN MEDIUM+ → PASS_WARNING | else → PASS_MAIN
- `server_score` tính để log/analytics — không dùng làm threshold

### D. Persistence Layer (`app/repositories/`)

**Thứ tự insert (quan trọng):**
1. `webhook_events` — raw, insert ngay khi nhận
2. `signals` — normalized
3. `signal_filter_results` — bulk insert
4. `signal_decisions` — 1 row per signal
5. `db.commit()` — commit business records trước notify
6. `telegram_messages` — sau khi send
7. `db.commit()` — commit delivery log

**Nguyên tắc:** Persist trước, notify sau. Không gửi Telegram trước khi DB commit.

### E. Telegram Notifier (`app/services/telegram_notifier.py`)

**Routing:**

| Decision | Channel |
|---|---|
| `PASS_MAIN` | `TELEGRAM_MAIN_CHAT_ID` |
| `PASS_WARNING` | `TELEGRAM_WARN_CHAT_ID` |
| `REJECT` + `LOG_REJECT_TO_ADMIN=true` | `TELEGRAM_ADMIN_CHAT_ID` |

**Retry policy:** Tối đa 3 lần, exponential backoff (1s, 2s, 4s).

---

## 3. Domain Models

### NormalizedSignal

```python
@dataclass
class NormalizedSignal:
    signal_id: str
    side: str               # "LONG" | "SHORT"
    symbol: str             # "BTCUSDT"
    timeframe: str          # "5m"
    price: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float | None
    indicator_confidence: float
    signal_type: str | None  # "LONG_V73" | "SHORT_V73" | "SHORT_SQUEEZE"
    strategy: str | None
    regime: str | None       # "STRONG_TREND_UP" | "WEAK_TREND_DOWN" | ...
    vol_regime: str | None   # "TRENDING_HIGH_VOL" | "SQUEEZE_BUILDING" | ...
    # ... indicators: atr, adx, rsi, rsi_slope, stoch_k, macd_hist
    # ... kc_position, atr_percentile, vol_ratio
    # ... squeeze_on, squeeze_fired, squeeze_bars
    source: str
    payload_timestamp: datetime
    bar_time: datetime | None
    raw_payload: dict
```

### FilterExecutionResult

```python
@dataclass
class FilterExecutionResult:
    filter_results: list[FilterResult]
    server_score: float
    final_decision: str     # DecisionType enum value
    decision_reason: str
    route: str              # TelegramRoute enum value
```

---

## 4. Enums

```python
class SignalSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class DecisionType(str, Enum):
    PASS_MAIN = "PASS_MAIN"
    PASS_WARNING = "PASS_WARNING"
    REJECT = "REJECT"
    DUPLICATE = "DUPLICATE"

class TelegramRoute(str, Enum):
    MAIN = "MAIN"
    WARN = "WARN"
    ADMIN = "ADMIN"
    NONE = "NONE"

class RuleResult(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

class RuleSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
```

---

## 5. Xử lý idempotency

**Idempotency key:** `signal_id` từ payload

**Khi nhận duplicate `signal_id`:**
- Return `200 accepted` với `decision: "DUPLICATE"`
- Không xử lý lại
- Không insert DB lần 2

---

## 6. Error Handling

| Loại lỗi | Hành động |
|---|---|
| Invalid secret | Return `401`, vẫn lưu `webhook_event` |
| Invalid JSON | Return `400 INVALID_JSON`, vẫn lưu `webhook_event` với `is_valid_json=false` |
| Invalid schema | Return `400 INVALID_SCHEMA`, vẫn lưu `webhook_event` với `is_valid_json=true` |
| Unsupported TF/symbol | Hiện tại đi qua filter/persist flow, không raise custom `400` |
| DB timeout | Retry 1 lần, nếu fail → return `500`, log |
| Telegram timeout | Retry 3 lần, nếu fail → log `FAILED` trong `telegram_messages` |
| Duplicate signal_id | Return `200` với `DUPLICATE`, không process |

---

## 7. Performance targets

| Metric | Target V1.1 |
|---|---|
| Webhook response time | < 500ms average |
| Telegram send time | < 2s (p95) |
| DB write (full flow) | < 200ms |
| Throughput | 50 req/min (burst từ nhiều TF cùng lúc) |

---

## 8. Security

- **HTTPS bắt buộc** cho webhook endpoint
- **Shared secret** trong payload body (không dùng HTTP header để tránh log exposure)
- Secret không được ghi vào application logs
- Admin endpoints chỉ expose internal hoặc dùng token auth
- Không hardcode secret trong code — luôn từ env/secret manager

---

## 9. Dependency Graph

```
webhook_controller
    └── auth_service
    └── signal_normalizer
    └── filter_engine
    │       └── signal_repo      (duplicate/cooldown check)
    │       └── market_event_repo (news block)
    │       └── config_repo      (thresholds)
    └── persistence (webhook_event_repo, signal_repo, filter_result_repo, decision_repo)
    └── telegram_notifier
            └── message_renderer
            └── telegram_repo    (delivery log)
```
