# Database Schema — Signal Bot V1

**Database:** PostgreSQL 16  
**Migration file:** `migrations/001_init.sql`

---

## Entity Relationship Overview

```
webhook_events (1)
    └──< signals (N)                   [webhook_event_id FK]
              └──< signal_filter_results (N)  [signal_row_id FK]
              └──  signal_decisions (1)        [signal_row_id FK UNIQUE]
              └──< telegram_messages (N)       [signal_row_id FK]
              └──  signal_outcomes (1)         [signal_row_id FK UNIQUE] ← V2 stub

system_configs (standalone key-value)
market_events  (standalone, dùng cho news block)
```

---

## 1. `webhook_events`

Raw log của mọi HTTP request từ TradingView.  
Insert ngay khi nhận, kể cả request invalid.

```sql
CREATE TABLE webhook_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    source_ip    VARCHAR(64),
    http_headers JSONB,
    raw_body     JSONB NOT NULL,
    is_valid_json BOOLEAN NOT NULL,
    auth_status  VARCHAR(32) NOT NULL,  -- "OK" | "INVALID_SECRET" | "MISSING"
    error_message TEXT
);
```

| Column | Ghi chú |
|---|---|
| `raw_body` | Toàn bộ body JSON thô. Lưu ngay cả khi invalid |
| `auth_status` | `"OK"` nếu secret đúng |
| `is_valid_json` | `false` nếu body không parse được |

---

## 2. `signals`

Normalized signal sau khi qua validation và parse thành công.

```sql
CREATE TABLE signals (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_event_id     UUID REFERENCES webhook_events(id),
    signal_id            VARCHAR(128) UNIQUE NOT NULL,
    source               VARCHAR(64) NOT NULL,
    symbol               VARCHAR(32) NOT NULL,
    chart_symbol         VARCHAR(32),
    exchange             VARCHAR(32),
    market_type          VARCHAR(32),
    timeframe            VARCHAR(16) NOT NULL,
    side                 VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    price                NUMERIC(18,8) NOT NULL,
    entry_price          NUMERIC(18,8) NOT NULL,
    stop_loss            NUMERIC(18,8) NOT NULL,
    take_profit          NUMERIC(18,8) NOT NULL,
    risk_reward          NUMERIC(10,4),
    indicator_confidence NUMERIC(6,4) NOT NULL,
    server_score         NUMERIC(6,4),
    signal_type          VARCHAR(64),           -- LONG_V73 | SHORT_V73 | SHORT_SQUEEZE
    strategy             VARCHAR(64),           -- RSI_STOCH_V73 | KELTNER_SQUEEZE
    regime               VARCHAR(64),
    vol_regime           VARCHAR(64),
    atr                  NUMERIC(18,8),
    atr_pct              NUMERIC(10,6),
    adx                  NUMERIC(10,4),
    rsi                  NUMERIC(10,4),
    rsi_slope            NUMERIC(10,4),
    stoch_k              NUMERIC(10,4),
    macd_hist            NUMERIC(18,8),
    kc_position          NUMERIC(10,6),
    atr_percentile       NUMERIC(10,4),
    vol_ratio            NUMERIC(10,4),
    squeeze_on           BOOLEAN,
    squeeze_fired        BOOLEAN,
    squeeze_bars         INTEGER,
    payload_timestamp    TIMESTAMP,
    bar_time             TIMESTAMP,
    raw_payload          JSONB NOT NULL,        -- full payload cho audit
    created_at           TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 3. `signal_filter_results`

Mỗi rule đã chạy được log thành 1 row.  
Dùng để debug, audit, và phân tích hiệu quả rule về sau.

```sql
CREATE TABLE signal_filter_results (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_row_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    rule_code    VARCHAR(64) NOT NULL,   -- xem FILTER_RULES.md Rule Code Catalog
    rule_group   VARCHAR(64) NOT NULL,   -- "validation" | "trading" | "routing"
    result       VARCHAR(16) NOT NULL CHECK (result IN ('PASS', 'WARN', 'FAIL')),
    severity     VARCHAR(16) NOT NULL CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    score_delta  NUMERIC(6,4) DEFAULT 0,
    details      JSONB,                  -- chi tiết tùy rule (threshold, actual value...)
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Ví dụ `details`:**
```json
{"required": 0.78, "actual": 0.76, "timeframe": "5m"}
{"rr_required": 1.5, "rr_actual": 1.23}
{"regime": "STRONG_TREND_DOWN", "side": "LONG"}
```

---

## 4. `signal_decisions`

Kết quả cuối cùng sau khi chạy toàn bộ filter.  
1 signal = 1 decision (UNIQUE).

```sql
CREATE TABLE signal_decisions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_row_id  UUID UNIQUE NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    decision       VARCHAR(32) NOT NULL CHECK (decision IN ('PASS_MAIN', 'PASS_WARNING', 'REJECT')),
    decision_reason TEXT,
    telegram_route VARCHAR(32) CHECK (telegram_route IN ('MAIN', 'WARN', 'ADMIN', 'NONE')),
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 5. `telegram_messages`

Log mỗi lần gửi message lên Telegram.  
1 signal có thể gửi nhiều kênh (VD: main + admin log).

```sql
CREATE TABLE telegram_messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_row_id       UUID REFERENCES signals(id) ON DELETE SET NULL,
    route               VARCHAR(32) NOT NULL,    -- "MAIN" | "WARN" | "ADMIN"
    chat_id             VARCHAR(64) NOT NULL,
    message_text        TEXT NOT NULL,
    telegram_message_id VARCHAR(64),             -- ID trả về từ Telegram API
    delivery_status     VARCHAR(32) NOT NULL CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'SKIPPED')),
    error_log           TEXT,
    sent_at             TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 6. `system_configs`

Config động, đọc từ DB thay vì hardcode.  
Cache 30s phía app.

```sql
CREATE TABLE system_configs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_key   VARCHAR(128) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description  VARCHAR(255),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Default config được insert trong migration:**
```sql
INSERT INTO system_configs (config_key, config_value)
VALUES ('signal_bot_config', '{
    "allowed_symbols": ["BTCUSDT", "BTCUSD"],
    "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m"],
    "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74},
    "cooldown_minutes":       {"1m": 5,    "3m": 8,    "5m": 10,   "12m": 20,   "15m": 25},
    "rr_min_base": 1.5,
    "rr_min_squeeze": 2.0,
    "duplicate_price_tolerance_pct": 0.2,
    "news_block_before_min": 15,
    "news_block_after_min": 30,
    "log_reject_to_admin": true
}'::jsonb);
```

---

## 7. `market_events`

Lịch sự kiện kinh tế nhập tay cho news block filter.

```sql
CREATE TABLE market_events (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name     VARCHAR(128) NOT NULL,
    start_time     TIMESTAMP NOT NULL,         -- UTC
    end_time       TIMESTAMP NOT NULL,         -- UTC
    impact         VARCHAR(16) NOT NULL,       -- "HIGH" | "MEDIUM" | "LOW"
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Bot query hiện tại:**
```sql
SELECT *
FROM market_events
WHERE start_time <= :window_end
  AND end_time >= :window_start;
```

---

## 8. `signal_outcomes` (V2 stub)

Chuẩn bị cho outcome tracking tự động ở V2.  
Schema hiện tại trong code/migration vẫn là bản stub tối giản.

```sql
CREATE TABLE signal_outcomes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_row_id UUID UNIQUE NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    is_win        BOOLEAN,
    pnl_pct       NUMERIC(10,4),
    exit_price    NUMERIC(18,8),
    closed_at     TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 9. Indexes

```sql
-- Query duplicate/cooldown check (hot path)
CREATE INDEX idx_signals_symbol_tf_side_created_at
ON signals(symbol, timeframe, side, created_at DESC);

-- Query theo signal_type cho cooldown
CREATE INDEX idx_signals_signal_type_created_at
ON signals(signal_type, created_at DESC);

-- Idempotency lookup
CREATE INDEX idx_signals_signal_id
ON signals(signal_id);

-- Filter results lookup
CREATE INDEX idx_signal_filter_results_signal_row_id
ON signal_filter_results(signal_row_id);

-- News block query
CREATE INDEX idx_market_events_active_window
ON market_events(is_active, start_time, end_time);

-- Telegram delivery lookup
CREATE INDEX idx_telegram_messages_signal_row_id
ON telegram_messages(signal_row_id);
```

---

## 10. Tracing audit trail

Từ 1 raw webhook → trace toàn bộ:

```sql
-- 1. Tìm raw event
SELECT * FROM webhook_events WHERE id = '<webhook_event_id>';

-- 2. Tìm normalized signal
SELECT * FROM signals WHERE webhook_event_id = '<webhook_event_id>';

-- 3. Xem từng rule đã chạy
SELECT rule_code, rule_group, result, severity, score_delta, details
FROM signal_filter_results
WHERE signal_row_id = '<signal_id>'
ORDER BY created_at;

-- 4. Xem decision
SELECT * FROM signal_decisions WHERE signal_row_id = '<signal_id>';

-- 5. Xem Telegram delivery
SELECT channel_type, delivery_status, sent_at, error_message
FROM telegram_messages WHERE signal_row_id = '<signal_id>';
```

---

## 11. Cleanup policy (tùy chọn)

V1 không bắt buộc, nhưng nên lên kế hoạch:

```sql
-- Xóa raw webhook events cũ (giữ 90 ngày)
DELETE FROM webhook_events
WHERE received_at < NOW() - INTERVAL '90 days'
  AND id NOT IN (SELECT webhook_event_id FROM signals WHERE webhook_event_id IS NOT NULL);

-- Xóa filter results cũ (giữ 90 ngày, signals vẫn còn)
DELETE FROM signal_filter_results
WHERE created_at < NOW() - INTERVAL '90 days';
```
