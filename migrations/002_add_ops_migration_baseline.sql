-- Migration 002: Operational migration baseline
-- Created: 2026-04-26

INSERT INTO system_configs (id, config_key, config_value, description)
VALUES (
    'ops-migration-baseline-001',
    'db_ops_baseline',
    '{
      "migration_strategy": "raw_sql_versioned",
      "runner": "scripts/db/migrate.py",
      "requires_restore_drill": true,
      "release_checklist": "docs/BACKUP_RECOVERY_RUNBOOK.md"
    }'::jsonb,
    'Operational baseline for versioned raw SQL migrations and restore drill discipline.'
)
ON CONFLICT (config_key) DO NOTHING;
