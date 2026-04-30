-- Query indexes for duplicate/cooldown lookup patterns.

CREATE INDEX IF NOT EXISTS idx_signals_dup_lookup
ON signals(symbol, timeframe, side, signal_type, created_at DESC, entry_price);
