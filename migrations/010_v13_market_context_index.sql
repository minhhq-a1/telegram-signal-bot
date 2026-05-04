-- Migration 010: Market context lookup index for V1.3 at-or-before-close checks.

CREATE INDEX IF NOT EXISTS idx_market_context_symbol_tf_source_bar_time
ON market_context_snapshots(symbol, timeframe, source, bar_time DESC);
