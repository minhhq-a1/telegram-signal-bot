-- Migration 009: Market context snapshot store for V1.2.

CREATE TABLE IF NOT EXISTS market_context_snapshots (
    id VARCHAR(36) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    timeframe VARCHAR(16) NOT NULL,
    bar_time TIMESTAMPTZ NOT NULL,
    backend_regime VARCHAR(64),
    backend_vol_regime VARCHAR(64),
    ema_fast NUMERIC(18,8),
    ema_mid NUMERIC(18,8),
    ema_slow NUMERIC(18,8),
    atr_pct NUMERIC(10,6),
    volume_ratio NUMERIC(10,4),
    source VARCHAR(64) NOT NULL,
    raw_context JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, timeframe, bar_time, source)
);
