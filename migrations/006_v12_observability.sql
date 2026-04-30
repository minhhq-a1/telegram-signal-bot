-- Migration 006: Observability foundations for V1.2.

ALTER TABLE webhook_events
ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(64);

ALTER TABLE signals
ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_webhook_events_correlation_id
ON webhook_events(correlation_id);

CREATE INDEX IF NOT EXISTS idx_signals_correlation_id
ON signals(correlation_id);
