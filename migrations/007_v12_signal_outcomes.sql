-- Migration 007: Expand signal_outcomes for V1.2 paper trading analytics.

ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS outcome_status VARCHAR(32);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS close_reason VARCHAR(32);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS entry_price NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS stop_loss NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS take_profit NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS max_favorable_price NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS max_adverse_price NUMERIC(18,8);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(10,4);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(10,4);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS r_multiple NUMERIC(10,4);
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS opened_at TIMESTAMPTZ;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_status
ON signal_outcomes(outcome_status);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_closed_at
ON signal_outcomes(closed_at);
