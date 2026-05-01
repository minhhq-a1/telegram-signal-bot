-- Migration 008: Config versioning and audit log for V1.2.

CREATE TABLE IF NOT EXISTS system_config_audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    config_key VARCHAR(128) NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by VARCHAR(128),
    change_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE system_configs ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS config_version INTEGER;
