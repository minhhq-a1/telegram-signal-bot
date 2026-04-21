-- Migration 001: Initial Schema
-- Created: 2026-04-20

-- 1. Webhook Events
CREATE TABLE IF NOT EXISTS webhook_events (
    id            VARCHAR(36) PRIMARY KEY,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_ip     VARCHAR(64),
    http_headers  JSONB,
    raw_body      JSONB NOT NULL,
    is_valid_json BOOLEAN NOT NULL DEFAULT TRUE,
    auth_status   VARCHAR(32) NOT NULL,
    error_message TEXT
);

-- 2. Signals
CREATE TABLE IF NOT EXISTS signals (
    id                   VARCHAR(36) PRIMARY KEY,
    webhook_event_id     VARCHAR(36) REFERENCES webhook_events(id),
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
    stop_loss            NUMERIC(18,8),
    take_profit          NUMERIC(18,8),
    risk_reward          NUMERIC(10,4),
    indicator_confidence NUMERIC(6,4) NOT NULL,
    server_score         NUMERIC(6,4),
    signal_type          VARCHAR(64),
    strategy             VARCHAR(64),
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
    payload_timestamp    TIMESTAMPTZ,
    bar_time             TIMESTAMPTZ,
    raw_payload          JSONB NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Signal Filter Results
CREATE TABLE IF NOT EXISTS signal_filter_results (
    id           VARCHAR(36) PRIMARY KEY,
    signal_row_id VARCHAR(36) NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    rule_code    VARCHAR(64) NOT NULL,
    rule_group   VARCHAR(64) NOT NULL,
    result       VARCHAR(16) NOT NULL CHECK (result IN ('PASS', 'WARN', 'FAIL')),
    severity     VARCHAR(16) NOT NULL CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    score_delta  NUMERIC(6,4) DEFAULT 0,
    details      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Signal Decisions
CREATE TABLE IF NOT EXISTS signal_decisions (
    id             VARCHAR(36) PRIMARY KEY,
    signal_row_id  VARCHAR(36) UNIQUE NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    decision       VARCHAR(32) NOT NULL CHECK (decision IN ('PASS_MAIN', 'PASS_WARNING', 'REJECT')),
    decision_reason TEXT,
    telegram_route VARCHAR(32) CHECK (telegram_route IN ('MAIN', 'WARN', 'ADMIN', 'NONE')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Telegram Messages
CREATE TABLE IF NOT EXISTS telegram_messages (
    id                  VARCHAR(36) PRIMARY KEY,
    signal_row_id       VARCHAR(36) REFERENCES signals(id) ON DELETE SET NULL,
    chat_id             VARCHAR(64) NOT NULL,
    route               VARCHAR(32) NOT NULL,
    message_text        TEXT NOT NULL,
    telegram_message_id VARCHAR(64),
    delivery_status     VARCHAR(32) NOT NULL CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'SKIPPED')),
    error_log           TEXT,
    sent_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. System Configs
CREATE TABLE IF NOT EXISTS system_configs (
    id           VARCHAR(36) PRIMARY KEY,
    config_key   VARCHAR(128) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description  VARCHAR(255),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Market Events
CREATE TABLE IF NOT EXISTS market_events (
    id             VARCHAR(36) PRIMARY KEY,
    event_name     VARCHAR(128) NOT NULL,
    start_time     TIMESTAMPTZ NOT NULL,
    end_time       TIMESTAMPTZ NOT NULL,
    impact         VARCHAR(16) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Signal Outcomes
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id                       VARCHAR(36) PRIMARY KEY,
    signal_row_id            VARCHAR(36) UNIQUE NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    is_win                   BOOLEAN,
    pnl_pct                  NUMERIC(10,4),
    exit_price               NUMERIC(18,8),
    closed_at                TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. Indexes (Strictly 6 as per Task requirements)
-- idx 1: Query duplicate/cooldown check
CREATE INDEX IF NOT EXISTS idx_signals_symbol_tf_side_created_at ON signals(symbol, timeframe, side, created_at DESC);
-- idx 2: Query theo strategy cho cooldown/analytics
CREATE INDEX IF NOT EXISTS idx_signals_strategy_created_at ON signals(strategy, created_at DESC);
-- idx 3: Idempotency lookup
CREATE INDEX IF NOT EXISTS idx_signals_signal_id ON signals(signal_id);
-- idx 4: Filter results lookup
CREATE INDEX IF NOT EXISTS idx_signal_filter_results_signal_row_id ON signal_filter_results(signal_row_id);
-- idx 5: News block query
CREATE INDEX IF NOT EXISTS idx_market_events_time_window ON market_events(start_time, end_time);
-- idx 6: Telegram delivery lookup
CREATE INDEX IF NOT EXISTS idx_telegram_messages_signal_row_id ON telegram_messages(signal_row_id);

-- Default Data
INSERT INTO system_configs (id, config_key, config_value)
VALUES (
    'default-config-001',
    'signal_bot_config',
    '{
    "allowed_symbols": ["BTCUSDT", "BTCUSD"],
    "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m"],
    "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74},
    "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25},
    "rr_min_base": 1.5,
    "rr_min_squeeze": 2.0,
    "duplicate_price_tolerance_pct": 0.002,
    "news_block_before_min": 15,
    "news_block_after_min": 30,
    "log_reject_to_admin": true
}'::jsonb
)
ON CONFLICT (config_key) DO NOTHING;
